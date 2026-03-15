from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import subprocess, uuid, os
from flask_migrate import Migrate
from datetime import date, datetime, timedelta, timezone
from collections import defaultdict
import json
import io
import sys
import traceback
import tempfile
from sqlalchemy.exc import IntegrityError 
import csv
import io
import pytz


app = Flask(__name__)
app.config['SECRET_KEY'] = 'pro_secret_key_99'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  

raw_db_url = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_DATABASE_URI'] = raw_db_url.replace("postgres://", "postgresql://", 1) if raw_db_url else 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 300,
    'pool_timeout': 20
}

db = SQLAlchemy(app)
login_manager = LoginManager(app)
migrate = Migrate(app, db)
login_manager.login_view = 'student_login'

# ==================== TIMEZONE HELPER (IST - CHENNAI) ====================
# Add this wherever you need to check the current time in your routes
ist = pytz.timezone('Asia/Kolkata')
current_time_ist = datetime.now(ist)

# For example, if you are passing 'now' to a template:
# return render_template('admin.html', grouped_tests=grouped_tests, now=current_time_ist)

def ist_now():
    """Forces the application to use exact Indian Standard Time (Chennai)."""
    return datetime.now(ist).replace(tzinfo=None)

@app.context_processor
def inject_now():
    """Injects IST time into all HTML templates automatically"""
    return {'now': ist_now()}


# ==================== DATABASE MODELS ====================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(50))

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(100))
    content = db.Column(db.Text)

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.String(20))
    title = db.Column(db.String(200))
    description = db.Column(db.Text)
    input_format = db.Column(db.Text)
    output_format = db.Column(db.Text)
    constraints = db.Column(db.Text)
    explanation = db.Column(db.Text)
    difficulty = db.Column(db.String(20))
    
    test_cases = db.relationship('TestCase', backref='question', lazy=True, cascade='all, delete-orphan')

class TestCase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    input_data = db.Column(db.Text)
    expected_output = db.Column(db.Text)
    is_sample = db.Column(db.Boolean, default=False)
    points = db.Column(db.Integer, default=10)
    question_root_id = db.Column(db.Integer, db.ForeignKey('question.id'))

class Testmaintain(db.Model):
    __tablename__ = 'test_maintain'
    id = db.Column(db.Integer, primary_key=True)
    test_title = db.Column(db.String(50))
    date = db.Column(db.Date)
    start_time = db.Column(db.DateTime)
    end_time = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='draft')
    total_points = db.Column(db.Integer, default=0)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)

    @property
    def is_currently_live(self):
        now = ist_now()
        if self.start_time and self.end_time and self.status == 'live':
            return self.start_time <= now <= self.end_time
        return False

class Student(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50))
    register = db.Column(db.String(50)) # String prevents postgres crashing on alphanumeric IDs
    username = db.Column(db.String(15), unique=True) 
    set_password = db.Column(db.String(100))
    verify_password = db.Column(db.String(100))
    department = db.Column(db.String(100))
    batch = db.Column(db.String(100)) 
    collage = db.Column(db.String(100)) 
    phone_no = db.Column(db.String(100)) 
    email = db.Column(db.String(60))
    approval = db.Column(db.Boolean, default=False)
    attend = db.Column(db.Boolean, default=False)
    
class Submission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.Text, nullable=False)
    language = db.Column(db.String(20))
    status = db.Column(db.String(20))
    timestamp = db.Column(db.DateTime, default=ist_now) # Forced IST
    marks_obtained = db.Column(db.Integer, default=0)
    total_marks = db.Column(db.Integer, default=0)
    test_cases_passed = db.Column(db.Integer, default=0)
    total_test_cases = db.Column(db.Integer, default=0)
    
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)
    test_id = db.Column(db.Integer, db.ForeignKey('test_maintain.id'), nullable=True)

    student = db.relationship('Student', backref='submissions')
    question = db.relationship('Question', backref='submissions')
    test = db.relationship('Testmaintain', backref='submissions')

class TestResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    test_id = db.Column(db.Integer, db.ForeignKey('test_maintain.id'), nullable=False)
    total_marks_obtained = db.Column(db.Integer, default=0)
    total_marks_possible = db.Column(db.Integer, default=0)
    percentage = db.Column(db.Float, default=0)
    status = db.Column(db.String(20), default='attempted')
    entry_time = db.Column(db.DateTime, default=ist_now) # Forced IST
    exit_time = db.Column(db.DateTime)
    submitted_at = db.Column(db.DateTime, default=ist_now) # Forced IST
    
    student = db.relationship('Student', backref='test_results')
    test = db.relationship('Testmaintain', backref='results')

# ==================== LOGIN MANAGER ====================

@login_manager.user_loader
def load_user(user_id):
    student = Student.query.get(int(user_id))
    if student:
        return student
    return User.query.get(int(user_id))

# ==================== INIT DATABASE ====================

with app.app_context():
    db.create_all()
    if not Student.query.filter_by(username='username').first():
        db.session.add(Student(username='username', set_password='password', name='Default Student', approval=True))
    
    if not User.query.filter_by(username='arun').first():
        db.session.add(User(username='arun', password='arun123'))
        
    db.session.commit()

# ==================== ROUTES ====================

@app.route('/')
def home():
    logout_user()
    return render_template('start_page.html')

@app.route('/student_login', methods=['GET', 'POST'])
def student_login():
    if current_user.is_authenticated:
        return redirect(url_for('student_test', id=current_user.id))
    
    if request.method == 'POST':
        user_in = request.form.get('username')
        pass_in = request.form.get('password')
        student = Student.query.filter_by(username=user_in, approval=True).first()
        if student and student.set_password == pass_in:
            login_user(student)
            return redirect(url_for('student_test', id=student.id))
        else:
            flash("Invalid username or password.", "danger")
    return render_template('student_login.html')

@app.route('/submission_try/<int:id>/<string:username>', methods=['POST','GET'])
def submission_try(id,username):
    q = Question.query.get_or_404(id)
    student = Student.query.filter_by(username=username).first_or_404()
    submissions = Submission.query.filter_by(question_id=id, student_id=student.id).order_by(Submission.timestamp.desc()).all()
    return render_template('submission_try.html', q=q, submissions=submissions, student=student)

@app.route('/student_problem_view/<int:id>', methods=['GET','POST'])
def student_problem_view(id):
    questions = Question.query.all()
    student = Student.query.get_or_404(id)
    test = Testmaintain.query.all()    
    return render_template("student_problem_view.html", questions=questions, student=student, test=test)

@app.route('/student_test/<int:id>') 
def student_test(id):
    student = Student.query.get_or_404(id)
    all_entries = Testmaintain.query.all()
    current_time = ist_now()
    grouped_tests = defaultdict(list)
    questions_dict = {q.id: q for q in Question.query.all()}
    for entry in all_entries:
        entry.question = questions_dict.get(entry.question_id)
        grouped_tests[entry.test_title].append(entry)
    results = TestResult.query.filter_by(student_id=id).all()
    test_question_ids = [entry.question_id for entry in all_entries]
    practice_questions = Question.query.filter(~Question.id.in_(test_question_ids)).all() if test_question_ids else Question.query.all()
    return render_template("student_test.html", student=student, grouped_tests=grouped_tests, practice_questions=practice_questions, results=results, now=current_time)

@app.route('/student_profile/<string:username>', methods=['GET','POST'])
def student_profile(username):
    student = Student.query.filter_by(username=username).first_or_404()
    return render_template('student_profile.html', student=student)

@app.route('/solve_and_compiler_page/<int:id>/<string:username>', methods=['GET','POST'])
def solve_and_compiler_page(id,username):
    q = Question.query.get_or_404(id)
    student = Student.query.filter_by(username=username).first_or_404()
    test_cases = TestCase.query.filter_by(question_root_id=id).all()
    test_id = request.args.get('test_id')
    current_test = Testmaintain.query.get(test_id) if test_id else None
    return render_template('solve_and_compiler_page.html', q=q, test_cases=test_cases, student=student, current_test=current_test)

@app.route('/admin')
@login_required
def admin_panel():
    messages = Message.query.all()
    questions = Question.query.all()
    students = Student.query.all()
    tests = Testmaintain.query.all()
    return render_template('admin.html', students=students, messages=messages, questions=questions, tests=tests)

@app.route('/student_overall_list', methods=['GET','POST'])
def student_overall_list():
    students = Student.query.all()
    return render_template('student_overall_list.html', students=students)


@app.route('/new_question', methods=['GET','POST'])
@login_required
def add_new_question():
    if request.method == 'POST':
        
        # --- 1. HANDLE CSV BULK IMPORT ---
        if 'import_btn' in request.form:
            file = request.files.get('question_file')
            
            if not file or file.filename == '':
                flash("No file uploaded", "danger")
                return redirect(url_for('add_new_question'))
            
            # Verify it is actually a CSV
            if file.filename.endswith('.csv'):
                try:
                    stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
                    csv_input = csv.DictReader(stream)
                    
                    success_count = 0
                    skip_count = 0
                    
                    for row in csv_input:
                        # Clean up header names and check question_id
                        q_id = row.get('question_id', '').strip()
                        if not q_id: 
                            continue
                        
                        # ANTI-DUPLICATE CHECK
                        existing_q = Question.query.filter_by(question_id=q_id).first()
                        if existing_q:
                            skip_count += 1
                            continue # Skip this row, ID already exists
                            
                        new_q = Question(
                            question_id=q_id,
                            title=row.get('title', ''),
                            description=row.get('description', ''),
                            input_format=row.get('input_format', ''),
                            constraints=row.get('constraints', ''),
                            output_format=row.get('output_format', ''),
                            explanation=row.get('explanation', ''),
                            difficulty=row.get('difficulty', 'Medium')
                        )
                        db.session.add(new_q)
                        db.session.flush() # Save to DB instantly to get new_q.id
                        
                        # Loop through up to 5 test cases from the CSV (input_1, output_1, etc.)
                        for i in range(1, 6): 
                            inp = row.get(f'input_{i}', '').strip()
                            outp = row.get(f'output_{i}', '').strip()
                            
                            if inp and outp:
                                db.session.add(TestCase(
                                    input_data=inp, 
                                    expected_output=outp, 
                                    is_sample=(i == 1), # Make the first one the sample case
                                    points=10, 
                                    question_root_id=new_q.id
                                ))
                        
                        success_count += 1
                        
                    db.session.commit()
                    
                    if success_count > 0:
                        flash(f"Successfully imported {success_count} questions! (Skipped {skip_count} duplicates)", "success")
                    else:
                        flash(f"No new questions added. All {skip_count} questions already existed.", "warning")
                        
                except Exception as e:
                    db.session.rollback()
                    flash(f"Error processing CSV. Please check your headers match exactly. Error: {str(e)}", "danger")
            else:
                flash("Invalid file format. Please upload a .csv file.", "danger")
                
            return redirect(url_for('admin_panel'))

        # --- 2. HANDLE MANUAL QUESTION ENTRY ---
        q_id = request.form.get('question_id').strip()
        
        # ANTI-DUPLICATE CHECK FOR MANUAL ENTRY
        existing_q = Question.query.filter_by(question_id=q_id).first()
        if existing_q:
            flash(f"Failed to add: A question with ID '{q_id}' already exists! Please use a unique ID.", "danger")
            return redirect(url_for('add_new_question'))
            
        new_q = Question(
            question_id=q_id, 
            title=request.form.get('title'), 
            description=request.form.get('description'), 
            input_format=request.form.get('input_format'), 
            constraints=request.form.get('constraints'), 
            output_format=request.form.get('output_format'), 
            explanation=request.form.get('explanation'), 
            difficulty=request.form.get('difficulty')
        )
        db.session.add(new_q)
        db.session.flush()
        
        inputs = request.form.getlist('test_inputs[]')
        outputs = request.form.getlist('test_outputs[]')
        
        for i in range(len(inputs)):
            if inputs[i].strip():
                db.session.add(TestCase(
                    input_data=inputs[i], 
                    expected_output=outputs[i], 
                    points=10, 
                    is_sample=(i == 0), 
                    question_root_id=new_q.id
                ))
                
        db.session.commit()
        flash("Question added successfully!", "success")
        return redirect(url_for('admin_panel'))

    return render_template('admin_question_add.html')



@app.route('/export_questions')
def export_questions():
    questions = Question.query.all()
    export_data = []
    for q in questions:
        test_cases = [{"input": c.input_data, "output": c.expected_output, "is_sample": c.is_sample, "points": c.points} for c in q.test_cases]
        export_data.append({"question_id": q.question_id, "title": q.title, "description": q.description, "input_format": q.input_format, "constraints": q.constraints, "output_format": q.output_format, "explanation": q.explanation, "difficulty": q.difficulty, "test_cases": test_cases})
    json_data = json.dumps(export_data, indent=4)
    return send_file(io.BytesIO(json_data.encode()), mimetype='application/json', as_attachment=True, download_name='questions_export.json')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and user.password == request.form.get('password'):
            login_user(user)
            return redirect(url_for('admin_panel'))
        flash('Invalid Credentials')
    return render_template('admin_login.html')

@app.route('/admin/update/<int:id>', methods=['GET', 'POST'])
@login_required
def update_question(id):
    question = Question.query.get_or_404(id)
    if request.method == 'POST':
        new_q_id = request.form.get('question_id', '').strip()
        
        # Anti-Duplicate Check: Ensure new ID isn't used by a DIFFERENT question
        if new_q_id != question.question_id:
            existing = Question.query.filter_by(question_id=new_q_id).first()
            if existing:
                flash(f"Error: The Question ID '{new_q_id}' is already assigned to another question!", "danger")
                return redirect(url_for('update_question', id=id))

        question.question_id = new_q_id
        question.title = request.form.get('title')
        question.description = request.form.get('description')
        question.input_format = request.form.get('input_format')
        question.constraints = request.form.get('constraints')
        question.output_format = request.form.get('output_format')
        question.explanation = request.form.get('explanation')
        question.difficulty = request.form.get('difficulty')
        
        # Delete old test cases and insert the new ones
        TestCase.query.filter_by(question_root_id=id).delete()
        inputs = request.form.getlist('test_inputs[]')
        outputs = request.form.getlist('test_outputs[]')
        
        for i in range(len(inputs)):
            if inputs[i].strip():
                db.session.add(TestCase(
                    input_data=inputs[i], 
                    expected_output=outputs[i], 
                    is_sample=(i == 0), 
                    points=10, 
                    question_root_id=question.id
                ))
                
        db.session.commit()
        flash("Question updated successfully!", "success")
        return redirect(url_for('every_question')) # Sends back to the Question Bank List
        
    return render_template('edit_questions.html', questions=question)

@app.route('/admin/student_approval/<int:id>', methods=['GET','POST'])
@login_required
def student_approval(id):
    student = Student.query.get_or_404(id)
    student.approval = True
    db.session.commit()
    flash(f"Student {student.name} approved!", "success")
    return redirect(url_for('admin_panel'))

@app.route('/admin/delete_student_stay/<int:id>')
@login_required
def delete_student_stay(id):
    db.session.delete(Student.query.get_or_404(id)); db.session.commit()
    return redirect(url_for('student_overall_list'))



@app.route('/admin/import_students', methods=['POST'])
@login_required
def import_students():
    # 1. Validate File Exists
    if 'student_csv' not in request.files:
        flash("No file was uploaded.", "danger")
        return redirect(url_for('student_overall_list'))

    file = request.files['student_csv']
    
    if file.filename == '':
        flash("No file was selected.", "danger")
        return redirect(url_for('student_overall_list'))

    if file and file.filename.endswith('.csv'):
        try:
            # 2. Read the CSV File stream
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            csv_input = csv.DictReader(stream)

            success_count = 0
            error_count = 0

            # 3. Iterate through rows and insert
            for row in csv_input:
                try:
                    # Clean up whitespace from the CSV columns
                    row = {k.strip().lower(): v.strip() for k, v in row.items() if k}
                    
                    # Ensure username is unique to prevent DB crash
                    existing_user = Student.query.filter_by(username=row.get('username')).first()
                    if existing_user:
                        error_count += 1
                        continue # Skip existing usernames

                    # Auto-Approve the student since the admin is adding them
                    new_student = Student(
                        name=row.get('name', ''),
                        register=row.get('register', ''),
                        username=row.get('username', ''),
                        set_password=row.get('password', ''),
                        verify_password=row.get('password', ''),
                        department=row.get('department', ''),
                        batch=row.get('batch', ''),
                        collage=row.get('collage', ''),
                        phone_no=row.get('phone_no', ''),
                        email=row.get('email', ''),
                        approval=True  
                    )
                    db.session.add(new_student)
                    success_count += 1
                    
                except Exception as row_error:
                    print(f"Row Error: {row_error}")
                    error_count += 1

            # Commit all the new students to the Database
            db.session.commit()
            
            if success_count > 0:
                flash(f"Success! Imported {success_count} students. (Skipped {error_count} duplicates/errors)", "success")
            else:
                flash("No students were imported. Ensure headers match the template.", "danger")
                
        except Exception as e:
            flash(f"Failed to read CSV format. Error: {str(e)}", "danger")
    else:
        flash("Invalid file type. Please upload a .csv file.", "danger")

    return redirect(url_for('student_overall_list'))



@app.route('/admin/delete_student/<int:id>')
@login_required
def delete_student(id):
    db.session.delete(Student.query.get_or_404(id)); db.session.commit()
    return redirect(url_for('admin_panel'))

@app.route('/show_all_questions', methods=['GET','POST'])
def every_question():
    questions = Question.query.all()
    return render_template('total_question.html', questions=questions)


@app.route('/admin/delete_question/<int:id>')
@login_required
def delete_question(id):
    # Find the question in the database
    question_to_delete = Question.query.get_or_404(id)
    
    try:
        # 1. Delete associated Test entries so the database doesn't crash
        Testmaintain.query.filter_by(question_id=id).delete()
        
        # 2. Delete associated student submissions for this question
        Submission.query.filter_by(question_id=id).delete()
        
        # 3. Delete the question itself (Test cases delete automatically)
        db.session.delete(question_to_delete)
        db.session.commit()
        
        flash("Question and its associated data were deleted successfully!", "success")
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting question: {e}")
        flash("An error occurred while trying to delete the question.", "danger")
        
    return redirect(url_for('every_question'))


@app.route('/create_test', methods=['GET', 'POST'])
def create_test():
    return render_template('create_test.html', questions=Question.query.all(), tests=Testmaintain.query.all())

@app.route('/add-test', methods=['POST'])
def add_test():
    test_title, question_ids, status = request.form.get('test_title'), request.form.getlist('question_ids[]'), request.form.get('status', 'draft')
    if not question_ids: return redirect(url_for('create_test'))
    total_points = 0
    for q_id in question_ids:
        question = Question.query.get(int(q_id))
        if question:
            points = sum(tc.points for tc in question.test_cases)
            total_points += points
            db.session.add(Testmaintain(test_title=test_title, date=date.today(), question_id=int(q_id), status=status, total_points=points))
    db.session.commit()
    flash(f"Test '{test_title}' created!", "success")
    return redirect(url_for('test_maintain'))

@app.route('/test_maintain')
@login_required
def test_maintain():
    all_entries = Testmaintain.query.all()
    
    # Use your existing time function here (like datetime.now() or ist_now())
    now = datetime.now() 
    
    # CRITICAL FIX: Fetch all questions and link them to the test entries
    questions_dict = {q.id: q for q in Question.query.all()}
    
    for entry in all_entries:
        # Update expired tests to 'completed'
        if entry.status == 'live' and entry.end_time and now > entry.end_time:
            entry.status = 'completed'
            
        # Attach the actual Question data so the HTML can read it!
        entry.question = questions_dict.get(entry.question_id)
        
    db.session.commit()
    
    # Group by test title
    grouped_tests = defaultdict(list)
    for entry in all_entries: 
        grouped_tests[entry.test_title].append(entry)
        
    return render_template('test_maintain.html', grouped_tests=grouped_tests, now=now)


@app.route('/delete-entire-test/<string:title>')
def delete_entire_test(title):
    Testmaintain.query.filter_by(test_title=title).delete(synchronize_session=False)
    db.session.commit(); return redirect(url_for('test_maintain'))

@app.route('/set-test-timing/<string:title>', methods=['POST'])
def set_test_timing(title):
    try:
        # Automatically slice the string to the first 16 chars (YYYY-MM-DDTHH:MM)
        # This completely eliminates the "seconds" bug causing silent crashes
        start_str = request.form.get('start_time')[:16]
        end_str = request.form.get('end_time')[:16]
        
        start_dt = datetime.strptime(start_str, '%Y-%m-%dT%H:%M')
        end_dt = datetime.strptime(end_str, '%Y-%m-%dT%H:%M')
        
        Testmaintain.query.filter_by(test_title=title).update({
            'start_time': start_dt, 
            'end_time': end_dt, 
            'status': request.form.get('status', 'scheduled')
        })
        db.session.commit()
        flash(f"Schedule for '{title}' updated successfully!", "success")
        
    except Exception as e:
        db.session.rollback()
        print(f"Schedule Update Error: {str(e)}")
        flash("Failed to update schedule. Please check the date format.", "danger")
        
    return redirect(url_for('test_maintain'))

@app.route('/delete-test-entry/<int:entry_id>')
def delete_test_entry(entry_id):
    db.session.delete(Testmaintain.query.get_or_404(entry_id)); db.session.commit()
    return redirect(url_for('test_maintain'))

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        db.session.add(Message(name=request.form.get('name'), content=request.form.get('content'), email=request.form.get('email')))
        db.session.commit(); flash('Message Sent!'); return redirect(url_for('student_problem_view', id=current_user.id))
    return render_template('contact.html')


# ==================== REGISTRATION ROUTE (FIXED) ====================
@app.route('/request_student', methods=['GET','POST'])
def request_student():
    if request.method == 'POST':
        try:
            new_student = Student(
                name=request.form.get('name'), 
                register=request.form.get('register'), 
                username=request.form.get('username'), 
                set_password=request.form.get('set_password'), 
                verify_password=request.form.get('verify_password'), 
                department=request.form.get('department'), 
                batch=request.form.get('batch'), 
                collage=request.form.get('collage'), 
                phone_no=request.form.get('phone_no'), 
                email=request.form.get('email')
            )
            db.session.add(new_student)
            db.session.commit()
            
            flash("Registration request submitted successfully!", "success")
            return redirect(url_for('home'))
            
        except IntegrityError:
            # Catches duplicate usernames or register numbers
            db.session.rollback()
            flash("Username or details already exist. Please choose a different username.", "danger")
            
        except Exception as e:
            # Catches Database Schema mismatches (like missing columns in Postgres)
            db.session.rollback()
            error_message = str(e)
            print(f"================ DATABASE ERROR ================\n{error_message}\n================================================")
            flash(f"Database Error: Failed to save. Please make sure your database is updated.", "danger")
            
    return render_template('request_student.html')


@app.route('/admin/delete_msg/<int:id>')
@login_required
def delete_msg(id):
    db.session.delete(Message.query.get_or_404(id)); db.session.commit()
    return redirect(url_for('admin_panel'))

@app.route('/logout')
def logout():
    logout_user(); return redirect(url_for('home'))

# ==================== TEST EXECUTION & RESULTS ====================

@app.route('/take-test/<string:title>')
@login_required
def take_test(title):
    test_entries = Testmaintain.query.filter_by(test_title=title).all()
    if not test_entries: return redirect(url_for('student_test', id=current_user.id))
    
    test = test_entries[0]
    now = ist_now()
    
    is_live = False
    if test.start_time and test.end_time and test.start_time <= now <= test.end_time:
        is_live = True
    
    # Record Entry Time for Tracking ONLY IF LIVE
    if is_live:
        res = TestResult.query.filter_by(test_id=test.id, student_id=current_user.id).first()
        if not res:
            db.session.add(TestResult(student_id=current_user.id, test_id=test.id, status='in_progress', entry_time=ist_now()))
            db.session.commit()

    questions = Question.query.filter(Question.id.in_([e.question_id for e in test_entries])).all()
    return render_template('take_test.html', test=test, questions=questions, student=current_user)

@app.route('/submit-test', methods=['POST'])
@login_required
def submit_test():
    test_id = request.form.get('test_id')
    test_main = Testmaintain.query.get(test_id)
    
    if not test_main:
        flash("Error locating test configuration.", "danger")
        return redirect(url_for('student_test', id=current_user.id))
        
    test_questions = Testmaintain.query.filter_by(test_title=test_main.test_title).all()
    
    total_obtained = 0
    total_possible = len(test_questions) * 10 
    
    report_data = []
    
    for entry in test_questions:
        q = Question.query.get(entry.question_id)
        code = request.form.get(f'code_{q.id}')
        lang = request.form.get(f'language_{q.id}', 'python')
        
        if code:
            cases = TestCase.query.filter_by(question_root_id=q.id).all()
            passed = 0
            
            for tc in cases:
                res = run_code_safe(code, lang, tc.input_data)
                if res['success'] and res['output'].strip() == tc.expected_output.strip():
                    passed += 1
            
            q_marks = 10 if passed > 0 else 0
            
            sub = Submission(
                code=code[:1000], 
                language=lang, 
                student_id=current_user.id, 
                question_id=q.id, 
                test_id=test_id, 
                marks_obtained=q_marks,
                total_marks=10, 
                test_cases_passed=passed, 
                total_test_cases=len(cases), 
                status='Accepted' if passed > 0 else 'Failed',
                timestamp=ist_now() # Using IST
            )
            db.session.add(sub)
            total_obtained += q_marks
            
            report_data.append(f"Question: {q.title}\nLanguage: {lang}\nTest Cases Passed: {passed}/{len(cases)}\nMarks: {q_marks}/10\n---\nCode Submitted:\n{code[:500]}\n...\n\n")

    res_record = TestResult.query.filter_by(test_id=test_id, student_id=current_user.id).first()
    if res_record:
        res_record.total_marks_obtained = total_obtained
        res_record.total_marks_possible = total_possible
        res_record.percentage = (total_obtained / total_possible * 100) if total_possible > 0 else 0
        res_record.status = 'passed' if res_record.percentage >= 40 else 'failed'
        res_record.exit_time = ist_now() # Using IST
        res_record.submitted_at = ist_now() # Using IST
    
    db.session.commit()
    
    try:
        results_dir = os.path.join(os.getcwd(), 'results')
        os.makedirs(results_dir, exist_ok=True)
        
        safe_title = "".join(c for c in test_main.test_title if c.isalnum() or c in (' ', '-', '_')).rstrip()
        safe_name = "".join(c for c in current_user.name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        filename = f"{safe_title}_{safe_name}_{current_user.register}.txt".replace(" ", "_")
        filepath = os.path.join(results_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"=== TEST RESULT REPORT ===\n")
            f.write(f"Student: {current_user.name} (Reg: {current_user.register})\n")
            f.write(f"Test: {test_main.test_title}\n")
            f.write(f"Final Score: {total_obtained} / {total_possible}\n")
            f.write(f"Status: {res_record.status.upper()}\n")
            f.write(f"Submitted At: {res_record.exit_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=========================\n\n")
            for text_block in report_data:
                f.write(text_block)
    except Exception as file_e:
        print(f"Failed to create physical result file: {str(file_e)}")

    return redirect(url_for('student_results', test_id=test_id))

@app.route('/student-results/<int:test_id>')
@login_required
def student_results(test_id):
    test = Testmaintain.query.get_or_404(test_id)
    result = TestResult.query.filter_by(test_id=test_id, student_id=current_user.id).first()
    submissions = Submission.query.filter_by(test_id=test_id, student_id=current_user.id).all()
    return render_template('student_results.html', test=test, result=result, submissions=submissions)

@app.route('/admin/test-results/<int:test_id>')
@login_required
def test_results(test_id):
    test = Testmaintain.query.get_or_404(test_id)
    results = TestResult.query.filter_by(test_id=test_id).all()
    return render_template('admin_test_results.html', test=test, results=results)

@app.route('/live-test/<string:title>')
@login_required
def live_test(title):
    test_group = Testmaintain.query.filter_by(test_title=title).all()
    if not test_group: 
        return redirect(url_for('test_maintain'))
        
    test_ids = [t.id for t in test_group]
    submissions = Submission.query.filter(Submission.test_id.in_(test_ids)).all()
    student_results = {}
    
    for sub in submissions:
        if sub.student_id not in student_results:
            student_results[sub.student_id] = {
                'student': sub.student, 
                'total_marks': 0, 
                'submissions': []
            }
        student_results[sub.student_id]['total_marks'] += sub.marks_obtained
        student_results[sub.student_id]['submissions'].append(sub)
        
    return render_template('live_monitor.html', title=title, test_group=test_group, student_results=student_results)

@app.route('/attendance_tracking', methods=['GET'])
@login_required
def attendance_tracking():
    tests = Testmaintain.query.with_entities(Testmaintain.test_title).distinct().all()
    test_titles = [t[0] for t in tests if t[0]]
    
    selected_title = request.args.get('test_title')
    test_id = request.args.get('test_id')
    
    if test_id and not selected_title:
        test_obj = Testmaintain.query.get(test_id)
        if test_obj:
            selected_title = test_obj.test_title
            
    if not selected_title and test_titles:
        selected_title = test_titles[0]
        
    attendance_data = []
    stats = {'total': 0, 'attended': 0, 'absent': 0, 'live': 0}
    
    if selected_title:
        all_students = Student.query.filter_by(approval=True).all()
        stats['total'] = len(all_students)
        
        test_entries = Testmaintain.query.filter_by(test_title=selected_title).all()
        test_ids = [t.id for t in test_entries]
        
        now = ist_now()
        test_end = test_entries[0].end_time if test_entries and test_entries[0].end_time else now
        
        if test_ids:
            for student in all_students:
                res = TestResult.query.filter(TestResult.student_id == student.id, TestResult.test_id.in_(test_ids)).first()
                
                if not res:
                    status = 'Absent'
                    stats['absent'] += 1
                elif res.exit_time is None:
                    if now > test_end:
                        status = 'Did Not Submit'
                        stats['absent'] += 1
                    else:
                        status = 'In Progress'
                        stats['live'] += 1
                else:
                    status = 'Completed'
                    stats['attended'] += 1
                    
                attendance_data.append({
                    'student': student,
                    'entry_time': res.entry_time if res else None,
                    'exit_time': res.exit_time if res else None,
                    'status': status
                })
                
    return render_template('attendance_tracking.html', 
                           test_titles=test_titles, 
                           selected_title=selected_title, 
                           attendance_data=attendance_data,
                           stats=stats)

@app.route('/run', methods=['POST'])
def run_code():
    data = request.json
    return jsonify(run_code_safe(data.get('code'), data.get('language'), data.get('input')))

def run_code_safe(code, language, input_data):
    uid = uuid.uuid4().hex
    res = {'success': False, 'output': '', 'error': ''}
    
    temp_dir = tempfile.gettempdir()
    
    try:
        if language == "python":
            filename = os.path.join(temp_dir, f"{uid}.py")
            with open(filename, "w", encoding='utf-8') as f: 
                f.write(code)
            p = subprocess.run(["python", filename], input=input_data, capture_output=True, text=True, timeout=5)
            res.update({'success': True, 'output': p.stdout, 'error': p.stderr})
            if os.path.exists(filename): os.remove(filename)

        elif language in ["c", "cpp"]:
            ext = ".c" if language == "c" else ".cpp"
            filename = os.path.join(temp_dir, f"{uid}{ext}")
            exe = os.path.join(temp_dir, f"{uid}.exe" if os.name == 'nt' else f"{uid}.out")
            with open(filename, "w", encoding='utf-8') as f: 
                f.write(code)
            compiler = "gcc" if language == "c" else "g++"
            compile_process = subprocess.run([compiler, filename, "-o", exe], capture_output=True, text=True, timeout=10)
            if compile_process.returncode == 0:
                run_process = subprocess.run([exe], input=input_data, capture_output=True, text=True, timeout=5)
                res.update({'success': True, 'output': run_process.stdout, 'error': run_process.stderr})
            else:
                res['error'] = compile_process.stderr
            if os.path.exists(filename): os.remove(filename)
            if os.path.exists(exe): os.remove(exe)

        elif language == "java":
            job_dir = os.path.join(temp_dir, uid)
            os.makedirs(job_dir, exist_ok=True)
            filename = os.path.join(job_dir, "Main.java")
            with open(filename, "w", encoding='utf-8') as f: 
                f.write(code)
            compile_process = subprocess.run(["javac", filename], capture_output=True, text=True, timeout=10)
            if compile_process.returncode == 0:
                run_process = subprocess.run(["java", "-cp", job_dir, "Main"], input=input_data, capture_output=True, text=True, timeout=5)
                res.update({'success': True, 'output': run_process.stdout, 'error': run_process.stderr})
            else:
                res['error'] = compile_process.stderr
            for file in os.listdir(job_dir):
                os.remove(os.path.join(job_dir, file))
            os.rmdir(job_dir)
            
    except subprocess.TimeoutExpired:
        res['error'] = "Time Limit Exceeded"
    except Exception as e: 
        res['error'] = str(e)
        
    return res

# --- EMERGENCY DATABASE RESET ROUTE ---
# Visit /admin/reset_db to rebuild the tables if Postgres crashes due to schema changes
@app.route('/admin/reset_db')
def reset_db():
    db.drop_all()
    db.create_all()
    if not Student.query.filter_by(username='username').first():
        db.session.add(Student(username='username', set_password='password', name='Default Student', approval=True))
    if not User.query.filter_by(username='arun').first():
        db.session.add(User(username='arun', password='arun123'))
    db.session.commit()
    return "Database has been completely reset and rebuilt with the latest columns."

if __name__ == "__main__":
    app.run(debug=True, host='127.0.0.1', port=5000, use_reloader=False)