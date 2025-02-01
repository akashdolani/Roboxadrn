from flask import Flask,redirect,render_template,url_for,session,flash,request,send_from_directory
import os
from flask_sqlalchemy import SQLAlchemy
from flask import jsonify
from flask_socketio import send,SocketIO,join_room

from sqlalchemy import Enum

from flask_login import UserMixin, login_user, LoginManager,login_required, logout_user, current_user
from webforms import LoginForm,RegistrationForm
from authlib.integrations.flask_client import OAuth

from datetime import datetime
from string import ascii_uppercase

from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash

from werkzeug.utils import secure_filename

from api_key import GITHUB_CLIENT_ID,GITHUB_CLIENT_SECRET,CLIENT_ID,CLIENT_SECRET

import random
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'mysecretkey'

UPLOAD_FOLDER = 'uploads'

# SQLite Database Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///iitd.db'
# Initialize the database
db = SQLAlchemy(app)



MAX_BUFFER_SIZE = 50 * 1000 * 1000  # 50 MB
socketio = SocketIO(app,max_http_buffer_size=MAX_BUFFER_SIZE)

migrate = Migrate(app, db)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
def allowed_file(filename):
    """
    Check if the uploaded file is allowed based on its extension.
    """
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Flask Login Stuff
login_manager = LoginManager()
login_manager.init_app(app)

app.config['LOGIN_VIEW'] = 'login'

oauth = OAuth(app)

google = oauth.register(
    name='google',
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    authorize_url='https://accounts.google.com/o/oauth2/v2/auth',
    access_token_url="https://oauth2.googleapis.com/token",
    authorization_base_url="https://accounts.google.com/o/oauth2/v2/auth",
    token_url="https://oauth2.googleapis.com/token",
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs = {'scope': 'openid profile email'},
    access_token_method="POST"
)

github = oauth.register(
    name='github',
    client_id=GITHUB_CLIENT_ID,
    client_secret=GITHUB_CLIENT_SECRET,
    authorize_url='https://github.com/login/oauth/authorize',
    authorize_params=None,
    access_token_url='https://github.com/login/oauth/access_token',
    access_token_params=None,
    client_kwargs={'scope': 'user:email'},
)



if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Database Models
# --------------------------------------------Models----------------------------------------


class Users(db.Model, UserMixin):
    #personal
    name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(120), nullable=False, unique=True)
    phoneNo = db.Column(db.Integer,nullable=True,unique=True)
    # job details
    id = db.Column(db.Integer, primary_key=True)
    designation = db.Column(db.String(200),nullable=True)
    department = db.Column(db.String(200),nullable=True)
    managerName = db.Column(db.String(200),nullable=True)
    dateJoin = db.Column(db.DateTime, default=datetime.now, nullable=True)
    # authentication
    userName = db.Column(db.String(20), nullable=False, unique=True)
    password_hash = db.Column(db.String(200),nullable=False)
    # Role
    role = db.Column(Enum("manager", "employee", name="role_types"), nullable=False)

    


    @property
    def password(self):
        raise AttributeError('password is not a readable attribute!')
    @password.setter
    def password(self, password):
         self.password_hash = generate_password_hash(password)
    
    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    # Create A String
    def __repr__(self):
        return '<Name %r>' % self.name




with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return Users.query.get(int(user_id))

@app.route('/login/google')
def login_google():
	try:
		redirect_uri = url_for('authorize_google', _external=True)
		return google.authorize_redirect(redirect_uri, prompt='select_account')
	except Exception as e:
		app.logger.error(f"Error during login: {str(e)}")
		return "Error occured during login", 500

# Authorize For Google
@app.route("/authorize/google")
def authorize_google():
	token = google.authorize_access_token()
	userinfo_endpoint = google.server_metadata['userinfo_endpoint']
	response = google.get(userinfo_endpoint)
	user_info = response.json()
	email = user_info['email']

	user = Users.query.filter_by(email=email).first()
	
	if user is None:
		user = Users(email=email, name=user_info['name'], password="")
		db.session.add(user)
		db.session.commit()
		flash("User Created Successfully!")
		login_user(user)
		return redirect(url_for('hello_world'))
	else:
		login_user(user)
		return redirect(url_for('hello_world'))



# Login Page
@app.route('/login', methods=['GET', 'POST'])
def login():
        loginform = LoginForm()
        signupform = RegistrationForm()

        if loginform.validate_on_submit():
            user = Users.query.filter_by(userName=loginform.username.data).first()
            if user:
                # Check the hash
                if check_password_hash(user.password_hash, loginform.password.data):
                    login_user(user)
                    session["name"] = loginform.username.data
                    session["id"] = user.id
                    # register -> home
                    if loginform.username.data == 'admin':
                        return redirect(url_for('dashboard', role='admin'))
                    else:
                        return redirect(url_for('dashboard', role='employee'))
                else:
                    flash("Wrong Credentials - Try Again!", "danger")
            else:
                flash("User Does Not Exist!", "danger")
        return render_template('login.html', loginform=loginform, signupform=signupform)

# Logout Page
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("You Have Been Logged Out!")
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    signupform = RegistrationForm()
    loginform = LoginForm()
    if signupform.validate_on_submit():
        username = signupform.username.data
        email = signupform.email.data
        if Users.query.filter_by(userName=username).first():
            flash("Username already exists. Please choose a different username.")
            return redirect(url_for('login'))
        if Users.query.filter_by(email=email).first():
            flash("Email already exists. Please choose a different Email.")
            return redirect(url_for('login'))
        hashed_password = generate_password_hash(signupform.password.data)
        new_user = Users(name=signupform.name.data,userName=signupform.username.data, email=signupform.email.data, password_hash=hashed_password, role='employee')
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        id = Users.query.filter_by(userName=username).first()
        session["name"] = username
        session["id"] = id.id
        # register->home
        return redirect(url_for('dashboard', role='employee'))
    
    return render_template('login.html', signupform=signupform, loginform=loginform)



@app.route("/")
def home():
    return redirect(url_for('login'))

@app.route("/dashboard/<role>")
def dashboard(role):
    return render_template('dashboard.html', role=role)

@app.route("/profile")
def profile():
    return render_template('profile.html')


@app.route("/upload_file", methods=["POST","GET"])
def upload_file():
    if 'file' not in request.files:
        return {"success": False, "message": "No file part"}
    
    file = request.files['file']
    
    if file.filename == '':
        return {"success": False, "message": "No selected file"}
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        file_url = url_for('uploaded_file', filename=filename)
        return {"success": True, "file_url": file_url}
    
    return {"success": False, "message": "File type not allowed"}

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)










## Create Custom Error Pages
# Invalid URL
@app.errorhandler(401)
def page_not_found(e):
	return redirect(url_for("login")),401

if __name__ == '__main__':
    socketio.run(app,debug=True)