import functools
from flask import Blueprint, render_template, redirect, url_for, flash, session
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo
from models import User
from extensions import db
from werkzeug.security import generate_password_hash, check_password_hash

auth_bp = Blueprint('auth', __name__)

class LoginForm(FlaskForm):
    username = StringField('用户名', validators=[DataRequired()])
    password = PasswordField('密码', validators=[DataRequired()])
    submit = SubmitField('登录')

class RegistrationForm(FlaskForm):
    username = StringField('用户名', validators=[DataRequired()])
    email = StringField('邮箱', validators=[DataRequired(), Email()])
    password = PasswordField('密码', validators=[DataRequired()])
    confirm_password = PasswordField('确认密码', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('注册')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            flash('登录成功!', 'success')
            return redirect(url_for('index'))
        else:
            flash('无效的用户名或密码。', 'error')
    
    return render_template('login.html', form=form)

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        username = form.username.data
        email = form.email.data
        password = form.password.data
        
        existing_user = User.query.filter((User.username == username) | (User.email == email)).first()
        if existing_user:
            flash('用户名或邮箱已存在。', 'error')
        else:
            new_user = User(username=username, email=email, password_hash=generate_password_hash(password))
            db.session.add(new_user)
            db.session.commit()
            flash('注册成功!', 'success')
            return redirect(url_for('auth.login'))
    
    return render_template('register.html', form=form)

@auth_bp.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('您已登出。', 'info')
    return redirect(url_for('index'))

class ResetPasswordForm(FlaskForm):
    old_password = PasswordField('旧密码', validators=[DataRequired()])
    new_password = PasswordField('新密码', validators=[DataRequired()])
    confirm_password = PasswordField('确认新密码', validators=[DataRequired(), EqualTo('new_password')])
    submit = SubmitField('重置密码')

def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        
        return view(**kwargs)
    
    return wrapped_view
@auth_bp.route('/reset_password', methods=['GET', 'POST'])

@login_required
def reset_password():
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user = User.query.get(session['user_id'])
        if user.check_password(form.old_password.data):
            user.set_password(form.new_password.data)
            db.session.commit()
            flash('您的密码已重置。', 'success')
            return redirect(url_for('index'))
        else:
            flash('无效的旧密码。', 'error')
    return render_template('reset_password.html', form=form)

