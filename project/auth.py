import uuid

from flask import Blueprint, redirect, render_template, request, url_for, flash
from flask_login import login_user, logout_user, login_required
from sqlalchemy import func
from werkzeug.security import generate_password_hash, check_password_hash
from .models import User, PasswordToken
from . import db

auth = Blueprint('auth', __name__)


@auth.route('/login')
def login():
    return render_template('login.html')


@auth.route('/login', methods=['POST'])
def login_post():
    # login code goes here
    email = request.form.get('email')
    password = request.form.get('password')
    remember = True if request.form.get('remember') else False

    user = User.query.filter(func.lower(User.email) == func.lower(email)).first()

    # check if the user actually exists
    # take the user-supplied password, hash it, and compare it to the hashed password in the database
    if not user or not check_password_hash(user.password, password):
        flash('Please check your login details and try again.')
        return redirect(url_for('auth.login')) # if the user doesn't exist or password is wrong, reload the page

    # if the above check passes, then we know the user has the right credentials
    login_user(user, remember=remember)

    # if the above check passes, then we know the user has the right credentials
    return redirect(url_for('main.index'))


@auth.route('/signup')
def signup():
    return render_template('signup.html')


@auth.route('/token')
@login_required
def create_password_token():
    password_token = PasswordToken(token=str(uuid.uuid4()))
    db.session.add(password_token)
    db.session.commit()
    return render_template('token.html', token=password_token.token)


@auth.route('/token/flush')
@login_required
def flush_password_tokens():
    # Delete all extant password tokens
    PasswordToken.query.delete()
    db.session.commit()

    # Go back to the homepage
    return redirect(url_for('main.index'))


@auth.route('/reset')
def reset():
    return render_template('reset.html')


@auth.route('/reset', methods=['POST'])
def reset_post():
    # code to validate and add user to database goes here
    token = request.form.get('token')
    email = request.form.get('email')
    password = request.form.get('password')

    # Verify that User and PasswordToken items exist in DB
    user = User.query.filter(func.lower(User.email) == func.lower(email)).first()
    password_token = PasswordToken.query.filter_by(token=token).first()

    # If we can't find the user, they need to try again
    if not user or not password_token:
        return redirect(url_for('auth.reset'))

    # create a new user with the form data. Hash the password so the plaintext version isn't saved.
    user.password = generate_password_hash(password, method='sha256')
    db.session.delete(password_token)

    # add the new user to the database
    db.session.add(user)
    db.session.commit()

    return redirect(url_for('auth.login'))


@auth.route('/signup', methods=['POST'])
def signup_post():
    # code to validate and add user to database goes here
    email = request.form.get('email')
    name = request.form.get('name')
    password = request.form.get('password')

    user = User.query.filter_by(email=email).first() # if this returns a user, then the email already exists in database

    if user: # if a user is found, we want to redirect back to signup page so user can try again
        return redirect(url_for('auth.signup'))

    # create a new user with the form data. Hash the password so the plaintext version isn't saved.
    new_user = User(email=email, name=name, password=generate_password_hash(password, method='sha256'))

    # add the new user to the database
    db.session.add(new_user)
    db.session.commit()

    return redirect(url_for('auth.login'))


@auth.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))
