from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
import pandas as pd
import json
from app.models import db
from app.models.feedback import FeedbackRepository, FeedbackQuestion, FeedbackResponse

feedback_bp = Blueprint('feedback', __name__)

def check_admin():
    return session.get('admin_logged_in')

@feedback_bp.route('/')
def list_repositories():
    if not check_admin():
        return redirect(url_for('auth.admin_login'))

    search_query = request.args.get('search', '').strip()
    query = FeedbackRepository.query

    if search_query:
        query = query.filter(FeedbackRepository.title.ilike(f'%{search_query}%'))

    repositories = query.order_by(FeedbackRepository.id.desc()).all()
    return render_template('feedback/list.html', repositories=repositories, search_query=search_query)


@feedback_bp.route('/create', methods=['GET', 'POST'])
def create_repository():
    if not check_admin():
        return redirect(url_for('auth.admin_login'))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()

        if not title:
            flash("Repository Title is required.", "danger")
            return redirect(url_for('feedback.create_repository'))

        repo = FeedbackRepository(title=title, description=description)
        db.session.add(repo)
        db.session.commit()

        # Handle CSV upload for questions
        csv_file = request.files.get('questions_csv')
        if csv_file and csv_file.filename:
            try:
                df = pd.read_csv(csv_file.stream)
                df.columns = [str(c).strip() for c in df.columns]
                
                for _, row in df.iterrows():
                    q_text = str(row.get('Question', '')).strip()
                    q_type = str(row.get('Type', 'MCQ')).strip().upper() # MCQ or TEXT
                    options = str(row.get('Options', '')).strip() # Comma separated options for MCQ

                    if not q_text:
                        continue

                    opt_list = [opt.strip() for opt in options.split(',') if opt.strip()] if options else ["Excellent", "Good", "Average", "Poor"]

                    question = FeedbackQuestion(
                        repo_id=repo.id,
                        question_text=q_text,
                        question_type=q_type if q_type in ['MCQ', 'TEXT'] else 'MCQ',
                        options_json=json.dumps(opt_list) if q_type == 'MCQ' else None
                    )
                    db.session.add(question)
                db.session.commit()
            except Exception as e:
                flash(f"Error reading Feedback CSV: {str(e)}", "warning")

        flash(f"Feedback Repository '{repo.title}' created successfully.", "success")
        return redirect(url_for('feedback.view_repository', repo_id=repo.id))

    return render_template('feedback/create_edit.html', repo=None)


@feedback_bp.route('/<int:repo_id>')
def view_repository(repo_id):
    if not check_admin():
        return redirect(url_for('auth.admin_login'))

    repo = FeedbackRepository.query.get_or_404(repo_id)
    questions = FeedbackQuestion.query.filter_by(repo_id=repo.id).all()
    responses = FeedbackResponse.query.filter_by(repo_id=repo.id).all()

    return render_template('feedback/detail.html', repo=repo, questions=questions, responses=responses)


@feedback_bp.route('/<int:repo_id>/add_question', methods=['POST'])
def add_question(repo_id):
    if not check_admin():
        return redirect(url_for('auth.admin_login'))

    repo = FeedbackRepository.query.get_or_404(repo_id)
    question_text = request.form.get('question_text', '').strip()
    question_type = request.form.get('question_type', 'MCQ').strip()
    options_raw = request.form.get('options', '').strip()

    if not question_text:
        flash("Question text is required.", "danger")
        return redirect(url_for('feedback.view_repository', repo_id=repo.id))

    opts_list = [o.strip() for o in options_raw.split(',') if o.strip()] if options_raw else ["Excellent", "Good", "Average", "Poor"]

    q = FeedbackQuestion(
        repo_id=repo.id,
        question_text=question_text,
        question_type=question_type,
        options_json=json.dumps(opts_list) if question_type == 'MCQ' else None
    )
    db.session.add(q)
    db.session.commit()

    flash("Question added to repository.", "success")
    return redirect(url_for('feedback.view_repository', repo_id=repo.id))


@feedback_bp.route('/<int:repo_id>/delete', methods=['POST'])
def delete_repository(repo_id):
    if not check_admin():
        return redirect(url_for('auth.admin_login'))

    repo = FeedbackRepository.query.get_or_404(repo_id)
    db.session.delete(repo)
    db.session.commit()
    flash(f"Feedback Repository '{repo.title}' deleted.", "success")
    return redirect(url_for('feedback.list_repositories'))
