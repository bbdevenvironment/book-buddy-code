from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import subprocess, uuid, os
from flask_migrate import Migrate
from datetime import date, datetime
from collections import defaultdict
import json
import io
import sys
import traceback
import tempfile
from sqlalchemy.exc import IntegrityError 

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
        now = datetime.now()
        if self.start_time and self.end_time and self.status == 'live':
            return self.start_time <= now <= self.end_time
        return False

class Student(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50))
    register = db.Column(db.String(50))
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
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())
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
    entry_time = db.Column(db.DateTime, default=db.func.current_timestamp())
    exit_time = db.Column(db.DateTime)
    submitted_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    
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
    current_time = datetime.now()
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
def add_new_question():
    if request.method == 'POST':
        if 'import_btn' in request.form:
            file = request.files.get('question_file')
            if not file: return "No file uploaded"
            data = json.load(file)
            for q in data:
                new_q = Question(question_id=q['question_id'], title=q['title'], description=q['description'], input_format=q['input_format'], constraints=q['constraints'], output_format=q['output_format'], explanation=q['explanation'], difficulty=q['difficulty'])
                db.session.add(new_q); db.session.flush()
                for case in q['test_cases']:
                    db.session.add(TestCase(input_data=case['input'], expected_output=case['output'], is_sample=case.get('is_sample', False), points=case.get('points', 10), question_root_id=new_q.id))
            db.session.commit()
            flash(f"Successfully imported {len(data)} questions!", "success")
            return redirect(url_for('admin_panel'))

        new_q = Question(question_id=request.form.get('question_id'), title=request.form.get('title'), description=request.form.get('description'), input_format=request.form.get('input_format'), constraints=request.form.get('constraints'), output_format=request.form.get('output_format'), explanation=request.form.get('explanation'), difficulty=request.form.get('difficulty'))
        db.session.add(new_q); db.session.flush()
        inputs = request.form.getlist('test_inputs[]')
        outputs = request.form.getlist('test_outputs[]')
        for i in range(len(inputs)):
            if inputs[i].strip():
                db.session.add(TestCase(input_data=inputs[i], expected_output=outputs[i], points=10, is_sample=(i == 0), question_root_id=new_q.id))
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
        question.question_id, question.title, question.description = request.form.get('question_id'), request.form.get('title'), request.form.get('description')
        question.input_format, question.constraints, question.output_format = request.form.get('input_format'), request.form.get('constraints'), request.form.get('output_format')
        question.explanation, question.difficulty = request.form.get('explanation'), request.form.get('difficulty')
        TestCase.query.filter_by(question_root_id=id).delete()
        inputs, outputs = request.form.getlist('test_inputs[]'), request.form.getlist('test_outputs[]')
        for i in range(len(inputs)):
            if inputs[i].strip():
                db.session.add(TestCase(input_data=inputs[i], expected_output=outputs[i], is_sample=(i == 0), points=10, question_root_id=question.id))
        db.session.commit()
        flash("Question updated successfully!", "success"); return redirect(url_for('admin_panel'))
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

@app.route('/admin/delete_student/<int:id>')
@login_required
def delete_student(id):
    db.session.delete(Student.query.get_or_404(id)); db.session.commit()
    return redirect(url_for('admin_panel'))

@app.route('/show_all_questions', methods=['GET','POST'])
def every_question():
    questions = Question.query.all()
    return render_template('total_question.html', questions=questions)

@app.context_processor
def inject_now():
    return {'now': datetime.now()}

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
def test_maintain():
    all_entries = Testmaintain.query.all()
    now = datetime.now()
    for entry in all_entries:
        if entry.status == 'live' and entry.end_time and now > entry.end_time:
            entry.status = 'completed'
    db.session.commit()
    grouped_tests = defaultdict(list)
    for entry in all_entries: grouped_tests[entry.test_title].append(entry)
    return render_template('test_maintain.html', grouped_tests=grouped_tests, now=now)


@app.route('/delete-entire-test/<string:title>')
def delete_entire_test(title):
    Testmaintain.query.filter_by(test_title=title).delete(synchronize_session=False)
    db.session.commit(); return redirect(url_for('test_maintain'))

@app.route('/set-test-timing/<string:title>', methods=['POST'])
def set_test_timing(title):
    start_dt = datetime.strptime(request.form.get('start_time'), '%Y-%m-%dT%H:%M')
    end_dt = datetime.strptime(request.form.get('end_time'), '%Y-%m-%dT%H:%M')
    Testmaintain.query.filter_by(test_title=title).update({'start_time': start_dt, 'end_time': end_dt, 'status': request.form.get('status', 'live')})
    db.session.commit(); return redirect(url_for('test_maintain'))

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
            # Catches duplicate usernames
            db.session.rollback()
            flash("Username already exists. Please choose a different username.", "danger")
            
        except Exception as e:
            # Catches missing columns, wrong data types, etc.
            db.session.rollback()
            print(f"DATABASE ERROR: {str(e)}") # This will print to your deployment server logs so you can read it
            flash("An error occurred while submitting your registration. Please try again.", "danger")
            
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
    
    # Record Entry Time for Tracking
    res = TestResult.query.filter_by(test_id=test_entries[0].id, student_id=current_user.id).first()
    if not res:
        db.session.add(TestResult(student_id=current_user.id, test_id=test_entries[0].id, status='in_progress'))
        db.session.commit()

    questions = Question.query.filter(Question.id.in_([e.question_id for e in test_entries])).all()
    return render_template('take_test.html', test=test_entries[0], questions=questions, student=current_user)



@app.route('/submit-test', methods=['POST'])
@login_required
def submit_test():
    test_id = request.form.get('test_id')
    test_main = Testmaintain.query.get(test_id)
    
    # Secure test lookup
    if not test_main:
        flash("Error locating test configuration.", "danger")
        return redirect(url_for('student_test', id=current_user.id))
        
    test_questions = Testmaintain.query.filter_by(test_title=test_main.test_title).all()
    
    total_obtained = 0
    total_possible = len(test_questions) * 10  # 10 marks per question
    
    # Store submission data for generating the text file report later
    report_data = []
    
    for entry in test_questions:
        q = Question.query.get(entry.question_id)
        code = request.form.get(f'code_{q.id}')
        lang = request.form.get(f'language_{q.id}', 'python')
        
        if code:
            cases = TestCase.query.filter_by(question_root_id=q.id).all()
            passed = 0
            
            # Check all test cases
            for tc in cases:
                res = run_code_safe(code, lang, tc.input_data)
                if res['success'] and res['output'].strip() == tc.expected_output.strip():
                    passed += 1
            
            # Requested Logic: If AT LEAST ONE test case passes, full 10 marks. Else 0.
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
                status='Accepted' if passed > 0 else 'Failed'
            )
            db.session.add(sub)
            total_obtained += q_marks
            
            # Prepare data for physical text file
            report_data.append(f"Question: {q.title}\nLanguage: {lang}\nTest Cases Passed: {passed}/{len(cases)}\nMarks: {q_marks}/10\n---\nCode Submitted:\n{code[:500]}\n...\n\n")

    # Update Database tracking records
    res_record = TestResult.query.filter_by(test_id=test_id, student_id=current_user.id).first()
    if res_record:
        res_record.total_marks_obtained = total_obtained
        res_record.total_marks_possible = total_possible
        res_record.percentage = (total_obtained / total_possible * 100) if total_possible > 0 else 0
        res_record.status = 'passed' if res_record.percentage >= 40 else 'failed'
        res_record.exit_time = datetime.now()
    
    db.session.commit()
    
    # ==== FILE CREATION LOGIC ====
    try:
        # Create a "results" folder in the main directory if it doesn't exist
        results_dir = os.path.join(os.getcwd(), 'results')
        os.makedirs(results_dir, exist_ok=True)
        
        # Name format: TestTitle_StudentName_StudentID.txt
        safe_title = "".join(c for c in test_main.test_title if c.isalnum() or c in (' ', '-', '_')).rstrip()
        safe_name = "".join(c for c in current_user.name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        filename = f"{safe_title}_{safe_name}_{current_user.register}.txt".replace(" ", "_")
        filepath = os.path.join(results_dir, filename)
        
        # Write the report data into the physical file
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
        # We don't want to crash the whole app just because writing a file failed, so we pass
    # ===============================

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
    
    # Get all submissions linked to any of the test IDs for this title
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
    # 1. Get unique test titles for the dropdown
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
        
        if test_ids:
            for student in all_students:
                # We only need ONE TestResult record per student per test title to know their status
                # Since TestResult currently binds to a specific test_id, we check if they have ANY result in the list of test_ids
                res = TestResult.query.filter(TestResult.student_id == student.id, TestResult.test_id.in_(test_ids)).first()
                
                if not res:
                    status = 'Absent'
                    stats['absent'] += 1
                elif res.exit_time is None:
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
    """Safe code execution using the OS temp directory to prevent Flask reloads"""
    uid = uuid.uuid4().hex
    res = {'success': False, 'output': '', 'error': ''}
    
    # Get the computer's safe temporary directory
    temp_dir = tempfile.gettempdir()
    
    try:
        if language == "python":
            # Save the file in the temp directory, NOT the project folder
            filename = os.path.join(temp_dir, f"{uid}.py")
            
            with open(filename, "w", encoding='utf-8') as f: 
                f.write(code)
                
            p = subprocess.run(["python", filename], input=input_data, capture_output=True, text=True, timeout=5)
            res.update({'success': True, 'output': p.stdout, 'error': p.stderr})
            
            if os.path.exists(filename): 
                os.remove(filename)

        elif language in ["c", "cpp"]:
            ext = ".c" if language == "c" else ".cpp"
            filename = os.path.join(temp_dir, f"{uid}{ext}")
            exe = os.path.join(temp_dir, f"{uid}.exe" if os.name == 'nt' else f"{uid}.out")
            
            with open(filename, "w", encoding='utf-8') as f: 
                f.write(code)
            
            compiler = "gcc" if language == "c" else "g++"
            compile_process = subprocess.run([compiler, filename, "-o", exe], capture_output=True, text=True, timeout=10)
            
            if compile_process.returncode == 0:
                # Run the compiled executable
                run_process = subprocess.run([exe], input=input_data, capture_output=True, text=True, timeout=5)
                res.update({'success': True, 'output': run_process.stdout, 'error': run_process.stderr})
            else:
                res['error'] = compile_process.stderr
                
            # Cleanup C/C++ files
            if os.path.exists(filename): os.remove(filename)
            if os.path.exists(exe): os.remove(exe)

        elif language == "java":
            # Java requires the file name to match the public class (Main)
            # So we create a unique temporary folder just for this run
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
                
            # Cleanup Java files
            for file in os.listdir(job_dir):
                os.remove(os.path.join(job_dir, file))
            os.rmdir(job_dir)
            
    except subprocess.TimeoutExpired:
        res['error'] = "Time Limit Exceeded (Code took too long to run)"
    except Exception as e: 
        res['error'] = str(e)
        
    return res
if __name__ == "__main__":
    app.run(debug=True, host='127.0.0.1', port=5000)