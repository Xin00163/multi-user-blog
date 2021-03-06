import os
import re
import random
import hashlib
import hmac
from string import letters

import webapp2
import jinja2

from google.appengine.ext import db

template_dir = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = jinja2.Environment(loader = jinja2.FileSystemLoader(template_dir),
                               autoescape = True)

secret = 'fart'

def render_str(template, **params):
    t = jinja_env.get_template(template)
    return t.render(params)

def make_secure_val(val):
    return '%s|%s' % (val, hmac.new(secret, val).hexdigest())

def check_secure_val(secure_val):
    val = secure_val.split('|')[0]
    if secure_val == make_secure_val(val):
        return val

class BlogHandler(webapp2.RequestHandler):
    def write(self, *a, **kw):
        self.response.out.write(*a, **kw)

    def render_str(self, template, **params):
        params['user'] = self.user
        return render_str(template, **params)

    def render(self, template, **kw):
        self.write(self.render_str(template, **kw))

    def set_secure_cookie(self, name, val):
        cookie_val = make_secure_val(val)
        self.response.headers.add_header(
            'Set-Cookie',
            '%s=%s; Path=/' % (name, cookie_val))

    def read_secure_cookie(self, name):
        cookie_val = self.request.cookies.get(name)
        return cookie_val and check_secure_val(cookie_val)

    def login(self, user):
        self.set_secure_cookie('user_id', str(user.key().id()))

    def logout(self):
        self.response.headers.add_header('Set-Cookie', 'user_id=; Path=/')

    def initialize(self, *a, **kw):
        webapp2.RequestHandler.initialize(self, *a, **kw)
        uid = self.read_secure_cookie('user_id')
        self.user = uid and User.by_id(int(uid))

def render_post(response, post):
    response.out.write('<b>' + post.subject + '</b><br>')
    response.out.write(post.content)

class MainPage(BlogHandler):
  def get(self):
      self.write('Hello, Udacity!')


##### user stuff
def make_salt(length = 5):
    return ''.join(random.choice(letters) for x in xrange(length))

def make_pw_hash(name, pw, salt = None):
    if not salt:
        salt = make_salt()
    h = hashlib.sha256(name + pw + salt).hexdigest()
    return '%s,%s' % (salt, h)

def valid_pw(name, password, h):
    salt = h.split(',')[0]
    return h == make_pw_hash(name, password, salt)

def users_key(group = 'default'):
    return db.Key.from_path('users', group)

class User(db.Model):
    name = db.StringProperty(required = True)
    pw_hash = db.StringProperty(required = True)
    email = db.StringProperty()

    @classmethod
    def by_id(cls, uid):
        return User.get_by_id(uid, parent = users_key())

    @classmethod
    def by_name(cls, name):
        u = User.all().filter('name =', name).get()
        return u

    @classmethod
    def register(cls, name, pw, email = None):
        pw_hash = make_pw_hash(name, pw)
        return User(parent = users_key(),
                    name = name,
                    pw_hash = pw_hash,
                    email = email)

    @classmethod
    def login(cls, name, pw):
        u = cls.by_name(name)
        if u and valid_pw(name, pw, u.pw_hash):
            return u


##### blog stuff

def blog_key(name = 'default'):
    return db.Key.from_path('blogs', name)

class Post(db.Model):
    subject = db.StringProperty(required = True)
    content = db.TextProperty(required = True)
    created = db.DateTimeProperty(auto_now_add = True)
    last_modified = db.DateTimeProperty(auto_now = True)
    user_id = db.IntegerProperty(required = True)


    def render(self):
        self._render_text = self.content.replace('\n', '<br>')
        return render_str("post.html", p = self)

class Like(db.Model):
    user_id = db.IntegerProperty(required = True)
    post_id = db.IntegerProperty(required = True)
    like_count = db.IntegerProperty(default=0)

class Comment(db.Model):
    user_id = db.IntegerProperty(required = True)
    post_id = db.IntegerProperty(required = True)
    content = db.TextProperty(required = True)
    created = db.DateTimeProperty(auto_now_add = True)
    last_modified = db.DateTimeProperty(auto_now = True)

class BlogFront(BlogHandler):
    def get(self):
        posts = greetings = Post.all().order('-created')
        self.render('front.html', posts = posts)

class PostPage(BlogHandler):
    def get(self, post_id):
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)

        if not post:
            self.error(404)
            return

        like_objs = db.Query(Like).filter('post_id =', int(post_id))

        total_likes = 0
        for like_obj in like_objs:
            total_likes += like_obj.like_count

        comments = Comment.gql("WHERE post_id = " + post_id)


        self.render("permalink.html", post = post,
                                      like_count = total_likes,
                                      comments = comments ) 

    def post(self,post_id):
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)

        if not post:
            self.error(404)
            return

        number1_button = self.request.get('like')
        number2_button = self.request.get('comment')

        if number1_button:
            print 'like pressed'
            if not self.user:
                self.redirect("/login?error=You need to be logged, in order" +
                              " to like your post!!")
            elif self.user.key().id() == post.user_id:
                self.redirect('/blog/%s?error=You cannot like your own post' % post_id)
            else:
                user_like_count = (
                    db.Query(Like)
                    .filter('post_id =', int(post_id))
                    .filter('user_id =', self.user.key().id())
                    .count()
                )
                #number 1 was pressed
                if user_like_count == 0:
                    #create a new Like object
                    like = Like(user_id = self.user.key().id(), post_id = int(post_id), like_count = 1)
                    like.put()

                self.redirect('/blog/%s' % post_id)


        elif number2_button:
            print "comment pressed"
            if not self.user:
                self.redirect("/login?error=You need to be logged, in order" +
                              " to delete your post!!")
            else:
                comment = self.request.get('comment')
                if comment:
                    print comment
                c = Comment(content = self.request.get('content'), post_id = int(post_id), user_id = self.user.key().id())
                c.put()
                self.redirect('/blog/%s' % post_id)
                #number 2 was pressed
                # see how you did it with posting new blog


class NewPost(BlogHandler):
    def get(self):
        if self.user:
            self.render("newpost.html")
        else:
            self.redirect("/login")

    def post(self):
        if not self.user:
            return self.redirect('/blog')

        subject = self.request.get('subject')
        content = self.request.get('content')

        if subject and content:
            p = Post(parent = blog_key(), subject = subject, content = content, user_id = self.user.key().id())
            p.put()
            self.redirect('/blog/%s' % str(p.key().id()))
        else:
            error = "subject and content, please!"
            self.render("newpost.html", subject=subject, content=content, error=error)

class DeletePost(BlogHandler):
    def get(self, post_id):
        if self.user:
            key = db.Key.from_path('Post', int(post_id), parent=blog_key())
            post = db.get(key)

            if not post:
                self.error(404)
                return

            if post.user_id == self.user.key().id():
                post.delete()
                self.redirect("/?deleted_post_id="+post_id)
            else:
                self.redirect("/blog/")
        else:
            self.redirect("/login?error=You need to be logged, in order" +
                          " to delete your post!!")


class EditPost(BlogHandler):
    def get(self, post_id):
        if self.user:
            key = db.Key.from_path('Post', int(post_id), parent=blog_key())
            post = db.get(key)

            if not post:
                self.error(404)
                return

            if post.user_id == self.user.key().id():
                self.render("editpost.html", subject=post.subject,
                            content=post.content)
            else:
                self.redirect("/blog/" + post_id + "?error=You don't have " +
                              "access to edit this record.")
        else:
            self.redirect("/login?error=You need to be logged, " +
                          "in order to edit your post!!")

    def post(self, post_id):
        """
            Updates post.
        """
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)

        if not post:
            self.error(404)
            return

        if not self.user:
            return self.redirect('/blog')

        if self.user.key().id() != post.user_id:
            return self.redirect('/blog?error=You cannot edit someone elses post')

        subject = self.request.get('subject')
        content = self.request.get('content')

        if subject and content:
            post.subject = subject
            post.content = content
            post.put()
            self.redirect('/blog/%s' % post_id)
        else:
            error = "subject and content, please!"
            self.render("editpost.html", subject=subject,
                        content=content, error=error)

class LikePost(BlogHandler):
    def get(self, post_id):
        if self.user:
            post_id = int(post_id)
            key = db.Key.from_path('Post', post_id, parent=blog_key())
            post = db.get(key)

            if not post:
                self.error(404)
                return

            if post.user_id == self.user.key().id():
                self.redirect('/blog/%s' % post_id)
            else:
                like = Like(user_id = self.user.key().id(), post_id = post_id)
                like.put()
                self.redirect('/blog/%s' % post_id)
        else:
            self.redirect("/login?error=You need to be logged, " +
                          "in order to like your post!!")


class NewComment(BlogHandler):
    def get(self):
        if self.user:
            self.render("permalink.html")
        else:
            self.redirect("/login")

    def post(self):
        if not self.user:
            return self.redirect('/blog')

        user_id = self.request.get('user_id')
        post_id = self.request.get('post_id')
        content = self.request.get('content')

        key = db.Key.from_path('Post', int(post_id))
        post = db.get(key)

        if not post:
            self.error(404)
            return

        if post_id and content:
            c = Comment(parent = blog_key(), post_id = post_id, content = content, user_id = self.user.key().id())
            c.put()
            self.redirect('/blog/%s' % str(c.key().id()))
        else:
            self.error ()

class DeleteComment(BlogHandler):
    def get(self, comment_id):
        if self.user:
            key = db.Key.from_path('Comment', int(comment_id))
            comment = db.get(key)

            if not comment:
                self.error(404)
                return

            if comment.user_id == self.user.key().id():
                comment.delete()
                self.redirect("/blog/"+str(comment.post_id)+"?deleted_comment_id=" +
                              str(comment_id))
            else:
                self.redirect("/blog/" + str(comment.post_id) + "?error=You don't have " +
                              "access to delete this comment.")
        else:
            self.redirect("/login?error=You need to be logged, in order to " +
                          "delete your comment!!")


class EditComment(BlogHandler):
    def get(self, comment_id):
        if self.user:
            key = db.Key.from_path('Comment', int(comment_id))
            comment = db.get(key)

            if not comment:
                self.error(404)
                return

            if comment.user_id == self.user.key().id():
                self.render("editcomment.html", content=comment.content)
            else:
                self.redirect("/blog/" + str(comment.post_id) +
                              "?error=You don't have access to edit this " +
                              "comment.")
        else:
            self.redirect("/login?error=You need to be logged, in order to" +
                          " edit your post!!")

    def post(self, comment_id):
        """
            Updates post.
        """
        if not self.user:
            self.redirect('/blog')

        key = db.Key.from_path('Comment',int(comment_id))
        c = db.get(key)

        if not c:
            self.error(404)
            return

        if self.user.key().id() != c.user_id:
            return self.redirect('/blog?error=You cannot edit someone elses comment')

        content = self.request.get('content')

        if content:
            c.content = content
            c.put()
            self.redirect('/blog/%s' % c.post_id)
        else:
            error = "subject and content, please!"
            self.render("editpost.html", subject=subject,
                        content=content, error=error)

###### Unit 2 HW's
class Rot13(BlogHandler):
    def get(self):
        self.render('rot13-form.html')

    def post(self):
        rot13 = ''
        text = self.request.get('text')
        if text:
            rot13 = text.encode('rot13')

        self.render('rot13-form.html', text = rot13)


USER_RE = re.compile(r"^[a-zA-Z0-9_-]{3,20}$")
def valid_username(username):
    return username and USER_RE.match(username)

PASS_RE = re.compile(r"^.{3,20}$")
def valid_password(password):
    return password and PASS_RE.match(password)

EMAIL_RE  = re.compile(r'^[\S]+@[\S]+\.[\S]+$')
def valid_email(email):
    return not email or EMAIL_RE.match(email)

class Signup(BlogHandler):
    def get(self):
        self.render("signup-form.html")

    def post(self):
        have_error = False
        self.username = self.request.get('username')
        self.password = self.request.get('password')
        self.verify = self.request.get('verify')
        self.email = self.request.get('email')

        params = dict(username = self.username,
                      email = self.email)

        if not valid_username(self.username):
            params['error_username'] = "That's not a valid username."
            have_error = True

        if not valid_password(self.password):
            params['error_password'] = "That wasn't a valid password."
            have_error = True
        elif self.password != self.verify:
            params['error_verify'] = "Your passwords didn't match."
            have_error = True

        if not valid_email(self.email):
            params['error_email'] = "That's not a valid email."
            have_error = True

        if have_error:
            self.render('signup-form.html', **params)
        else:
            self.done()

    def done(self, *a, **kw):
        raise NotImplementedError

class Unit2Signup(Signup):
    def done(self):
        self.redirect('/unit2/welcome?username=' + self.username)

class Register(Signup):
    def done(self):
        #make sure the user doesn't already exist
        u = User.by_name(self.username)
        if u:
            msg = 'That user already exists.'
            self.render('signup-form.html', error_username = msg)
        else:
            u = User.register(self.username, self.password, self.email)
            u.put()

            self.login(u)
            self.redirect('/blog')

class Login(BlogHandler):
    def get(self):
        self.render('login-form.html')

    def post(self):
        username = self.request.get('username')
        password = self.request.get('password')

        u = User.login(username, password)
        if u:
            self.login(u)
            self.redirect('/blog')
        else:
            msg = 'Invalid login'
            self.render('login-form.html', error = msg)

class Logout(BlogHandler):
    def get(self):
        self.logout()
        self.redirect('/blog')

class Unit3Welcome(BlogHandler):
    def get(self):
        if self.user:
            self.render('welcome.html', username = self.user.name)
        else:
            self.redirect('/signup')

class Welcome(BlogHandler):
    def get(self):
        username = self.request.get('username')
        if valid_username(username):
            self.render('welcome.html', username = username)
        else:
            self.redirect('/unit2/signup')

app = webapp2.WSGIApplication([('/', MainPage),
                               ('/unit2/rot13', Rot13),
                               ('/unit2/signup', Unit2Signup),
                               ('/unit2/welcome', Welcome),
                               ('/blog/?', BlogFront),
                               ('/blog/([0-9]+)', PostPage),
                               ('/blog/newpost', NewPost),
                               ('/blog/deletepost/([0-9]+)', DeletePost),
                               ('/blog/editpost/([0-9]+)', EditPost),
                               ('/blog/like/([0-9]+)', LikePost),
                               ('/blog/deletecomment/([0-9]+)', DeleteComment),
                               ('/blog/editcomment/([0-9]+)', EditComment),
                               ('/signup', Register),
                               ('/login', Login),
                               ('/logout', Logout),
                               ('/unit3/welcome', Unit3Welcome),
                               ],
                              debug=True)
