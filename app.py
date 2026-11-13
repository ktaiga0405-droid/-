from flask import Flask, request, render_template, session, redirect, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import date
from werkzeug.security import(generate_password_hash,check_password_hash)
from dotenv import load_dotenv
import secrets, os

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ['SECRET_KEY'] 
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URI']

db = SQLAlchemy(app)

class Class(db.Model):
    __tablename__ = 'classes'
    id = db.Column(db.Integer, primary_key=True)
    class_name = db.Column(db.String(100), nullable=False)
    task_type = db.Column(db.String(50), nullable=False)  
    deadlines = db.Column(db.Date, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('user_groups.id'), nullable=True)
    is_completed = db.Column(db.Boolean, default=False, nullable=False)

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)

class User_group(db.Model):
    __tablename__ = 'user_groups'
    id = db.Column(db.Integer, primary_key=True)
    group_name = db.Column(db.String(100), nullable=False)
    invite_code = db.Column(db.String(24), unique=True, nullable=False, default=lambda: secrets.token_hex(12))

class Group_member(db.Model):
    __tablename__ = 'group_members'
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'),primary_key=True, nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('user_groups.id'), primary_key=True, nullable=False)

class Task_completion(db.Model):
    __tablename__ = 'task_completions'
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

@app.route('/home')
def home_page():
    if 'user_id' not in session:
        return redirect('/login_open')
    today = date.today()
    username = None
    group_name = None
    members = None
    upcoming_task = None
    groups = None
    incomplete_count=0
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if user:
            username = user.username
            groups = User_group.query.filter(User_group.id.in_(Group_member.query.filter(Group_member.user_id == session['user_id']).with_entities(Group_member.group_id))).all()

    if 'group_id' in session:
        group = User_group.query.get(session['group_id'])
        upcoming_task = Class.query.filter_by(group_id=session['group_id'], is_completed=False).filter(Class.deadlines >= today).order_by(Class.deadlines).first()
        if group:
            group_name = group.group_name
            members = User.query.join(Group_member).filter(Group_member.group_id == group.id).all()
            incomplete_count=Class.query.filter_by(group_id=group.id, is_completed=False).count()
    else:
        upcoming_task = Class.query.filter_by(user_id=session['user_id'], group_id=None, is_completed=False).filter(Class.deadlines >= today).order_by(Class.deadlines).first()
        incomplete_count=Class.query.filter_by(user_id=session['user_id'],group_id=None, is_completed=False).count()
    if incomplete_count==0:
        incomplete_result="すべて完了！"
    else:
        incomplete_result=str(incomplete_count)+"件"
    return render_template('home.html', username=username, today=today, group_name=group_name, members=members if 'group_id' in session else None, incomplete_result=incomplete_result, upcoming_task=upcoming_task, groups=groups)

@app.route('/')
def home():
    return redirect('/home')

@app.route('/group')
def group():
    if 'user_id' not in session:
        return redirect('/login_open')
    groups = User_group.query.filter(User_group.id.in_(Group_member.query.filter(Group_member.user_id == session['user_id']).with_entities(Group_member.group_id))).all()
    invite_code = None
    selected_group_name = None
    selected_group_id = session.get('group_id')
    if 'group_id' in session:
        group = User_group.query.get(session['group_id'])
        if group is not None:
            member = Group_member.query.filter_by(user_id=session['user_id'], group_id=group.id).first()
            if member:
                invite_code = group.invite_code
                selected_group_name = group.group_name
                selected_group_id=group.id
            else:
                session.pop('group_id', None)
        else:
            session.pop('group_id', None)
    return render_template('group.html', groups=groups, invite_code=invite_code, selected_group_name=selected_group_name, selected_group_id=selected_group_id)

@app.route('/personal', methods=['POST'])
def switch_to_personal():
    if 'user_id' not in session:
        return redirect('/login_open')
    session.pop('group_id', None)
    return redirect('/home')

@app.route('/select_group/<int:group_id>', methods=['POST'])
def select_group(group_id):
    if 'user_id' not in session:
        return redirect('/login_open')

    member = Group_member.query.filter_by(user_id=session['user_id'], group_id=group_id).first()
    if member:
        session['group_id'] = group_id
    return redirect('/home')

@app.route('/create_group', methods=['POST'])
def create_group():
    if 'user_id' not in session:
        return redirect('/login_open')

    group_name = request.form['group_name'].strip()
    if not group_name:
        flash('※グループ名を入力してください')
        return redirect('/group')

    new_group = User_group(group_name=group_name)
    db.session.add(new_group)
    db.session.commit()

    member = Group_member(user_id=session['user_id'], group_id=new_group.id)
    db.session.add(member)
    db.session.commit()

    session['group_id'] = new_group.id
    flash('グループが作成されました。')
    return redirect('/group')

@app.route('/join_group', methods=['POST'])
def join_group():
    if 'user_id' not in session:
        return redirect('/login_open')

    group_name = request.form['group_name'].strip()
    invite_code = request.form['invite_code'].strip()

    if not group_name:
        flash('※グループ名を入力してください')
        return redirect('/group')
    
    if not invite_code:
        flash('※招待コードを入力してください')
        return redirect('/group')

    group = User_group.query.filter_by(group_name=group_name, invite_code=invite_code).first()
    if group:
        member = Group_member.query.filter_by(user_id=session['user_id'], group_id=group.id).first()
        if member:
            flash('※既にこのグループに参加しています')
            return redirect('/group')
        new_member = Group_member(user_id=session['user_id'], group_id=group.id)
        db.session.add(new_member)
        db.session.commit()
        session['group_id'] = group.id
        return redirect('/group')
    else:
        flash('※グループ名または招待コードが正しくありません')
        return redirect('/group')

@app.route('/leave/<int:group_id>', methods=['POST'])
def leave_group(group_id):
    if 'user_id' not in session:
        return redirect('/login_open')

    group_member = Group_member.query.filter_by(user_id=session['user_id'], group_id=group_id).first()
    if group_member:
        db.session.delete(group_member)
        db.session.commit()

        if session.get('group_id') == group_id:
            session.pop('group_id', None)
            flash("グループを退会しました")

    return redirect('/group')


@app.route('/acount_open')
def acount_open():
    return render_template('acount.html')

@app.route('/acount', methods=['POST'])
def acount():
    today = date.today()
    session.clear()
    username = request.form['username'].strip()
    password = request.form['password'].strip()
    if not username:
        flash('※ユーザーネームを入力してください')
        return redirect('/acount_open')
    if not password:
        flash('※パスワードを入力してください')
        return redirect('/acount_open')
    existing_user=User.query.filter_by(username=username).first()
    if existing_user:
        flash('※このユーザー名は既に使用されています')
        return redirect('/acount_open')
    
    hashed_password=generate_password_hash(password)
    
    new_user = User(username=username, password=hashed_password)
    db.session.add(new_user)
    db.session.commit()
    session['user_id'] = new_user.id
    return redirect('/home')

@app.route('/login_open')
def login_open():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    date_today = date.today()
    username = request.form['username'].strip()
    password = request.form['password'].strip()
    if not username:
        flash('※ユーザー名を入力してください')
        return redirect('/login_open')
    if not password:
        flash('※パスワードを入力してください')
        return redirect('/login_open')
    user = User.query.filter_by(username=username).first()
    if user and check_password_hash(user.password,password):
        session.clear()
        session['user_id'] = user.id
        return redirect('/home')
    else:
        flash('※ユーザー名またはパスワードが正しくありません')
        return redirect('/login_open')

@app.route('/logout',methods=['POST'])
def logout():
    session.clear()
    return redirect('/login_open')


@app.route('/list')
def list():
    if 'user_id' not in session:
        return redirect('/login_open')
    today = date.today()
    progress={}
    if session.get('group_id') is not None:
        classes = Class.query.filter_by(group_id=session['group_id'], is_completed=False).order_by(Class.deadlines).all()
        for task in classes:
            if task.group_id is not None:
                member_count=Group_member.query.filter_by(group_id=task.group_id).count()
                completion_count=Task_completion.query.join(Group_member,Task_completion.user_id==Group_member.user_id).filter(Task_completion.task_id==task.id, Group_member.group_id==task.group_id).count()
                my_completion=Task_completion.query.filter_by(task_id=task.id,user_id=session['user_id']).first()
                progress[task.id]={'rest':member_count-completion_count,'my_completion':my_completion is not None}
    else:
        classes = Class.query.filter_by(user_id=session['user_id'], group_id=None, is_completed=False).order_by(Class.deadlines).all()
    return render_template('list.html', class_names=classes, today=today, progress=progress)


@app.route('/add_list', methods=['POST'])
def add_class():
    if 'user_id' not in session:
        return redirect('/login_open')
    today = date.today()
    class_name = request.form['class_name'].strip()
    task_type = request.form.get('option')
    deadlines = request.form.get('deadline')
    if not class_name:
        flash('※授業名を入力してください')
        return redirect('/home')
    if len(class_name)>100:
        flash('※授業名が長すぎます')
        return redirect('/home')
    if not task_type:
        flash('※課題を選択してください')
        return redirect('/home')
    if not deadlines:
        flash('※期限日を選択してください')
        return redirect('/home')
    new_class = Class(class_name=class_name, task_type=task_type, deadlines=deadlines, user_id=session['user_id'], group_id=session.get('group_id'))
    db.session.add(new_class)
    db.session.commit()
    return redirect('/list')
    

@app.route('/destroy/<int:id>', methods=['POST'])
def delete_class(id):
    user_id = session.get('user_id')
    if user_id is None:
        return redirect('/login_open')

    task=db.session.get(Class,id)
    if task is None:
        flash('完了する権限がありません。')
        return redirect(f'/destroy/{id}')

    if task.group_id is None:
        if task.user_id != user_id:
            flash('完了する権限がありません。')
            return redirect(f'/destroy/{id}')
    else:
        member = Group_member.query.filter_by(user_id=user_id, group_id=task.group_id).first()
        if member is None:
            flash('完了する権限がありません。')
            return redirect(f'/destroy/{id}')

    existing=Task_completion.query.filter_by(task_id=id, user_id=user_id).first()
    if existing:
        return redirect('/list')
    completion = Task_completion(task_id=id, user_id=user_id)
    db.session.add(completion)
    db.session.commit()

    if task.group_id is not None:
        member_count=Group_member.query.filter_by(group_id=task.group_id).count()
        completion_count=Task_completion.query.join(Group_member, Task_completion.user_id == Group_member.user_id).filter(Task_completion.task_id == id,Group_member.group_id == task.group_id).count()
        if member_count > 0 and completion_count == member_count:
            message = f"グループの全員が課題「{task.class_name}」を完了しました!!"
            task.is_completed = True
        else:
            remaining_count = member_count - completion_count
            message = f"課題「{task.class_name}」を完了しました! 残り{remaining_count}人が未完了です!"
    else:
        message = f"課題「{task.class_name}」を完了しました!!"
        task.is_completed = True
    
    db.session.commit()

    flash(message)
    return redirect('/list')
    

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit_class(id):
    if 'user_id' not in session:
        return redirect('/login_open')
    cls = get_current_task(id)
    if cls is None:
        flash('完了する権限がありません。')
        return redirect('/home')
    return render_template('edit.html', cls=cls)

@app.route('/edit/task/<int:id>', methods=['POST'])
def update_class(id):
    if 'user_id' not in session:
        return redirect('/login_open')
    cls = get_current_task(id)
    if cls is None:
        flash('完了する権限がありません。')
        return redirect(f'/edit/{id}')
    class_name = request.form['class_name'].strip()
    task_type = request.form.get('option')
    deadlines = request.form.get('deadline')
    if not class_name:
        flash("※授業名を入力してください")
        return redirect(f'/edit/{id}')
    if not task_type:
        flash("※課題を選択してください")
        return redirect(f'/edit/{id}')
    if not deadlines:
        flash('※期限日を選択してください')
        return redirect(f'/edit/{id}')
    cls.class_name = class_name
    cls.task_type = task_type
    cls.deadlines = deadlines
    db.session.commit()
    flash('課題が更新されました')
    return redirect('/list')

def get_current_task(id):
    user_id = session['user_id']
    group_id = session.get('group_id')

    if group_id is not None:
        member=Group_member.query.filter_by(user_id=user_id,group_id=group_id).first()

        if member is None:
            session.pop('group_id', None)
            return None
        
        return Class.query.filter_by(id=id,group_id=group_id).first()
    else:
        return Class.query.filter_by(id=id,user_id=user_id,group_id=None).first()


if __name__ == '__main__':
    app.run(debug=True)


