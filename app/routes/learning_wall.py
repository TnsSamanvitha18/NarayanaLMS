from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash
from app.models import db
from app.models.learning_wall import LearningWallPost, LearningWallReaction
from app.models.user import Learner
from app.services.learning_wall_service import (
    seed_sample_wall_posts_if_empty,
    check_and_generate_birthday_posts,
    toggle_post_reaction,
    clear_all_wall_posts
)

learning_wall_bp = Blueprint('learning_wall', __name__)

@learning_wall_bp.route('/')
def index():
    """
    Renders the automated news-bulletin Learning Wall feed.
    Accessible to both logged-in Learners and Admins.
    """
    # Require login (Admin or Learner)
    if not session.get('admin_logged_in') and not session.get('learner_id') and not session.get('learner_global_id'):
        flash("Please log in to view the Learning Wall feed.", "info")
        return redirect(url_for('auth.learner_login'))

    # 1. Seed initial milestone posts if empty & check today's birthdays
    seed_sample_wall_posts_if_empty()
    check_and_generate_birthday_posts()

    # 2. Query posts ordered newest first
    posts = LearningWallPost.query.order_by(LearningWallPost.created_at.desc()).all()

    # 3. Resolve user details (Learner or Admin)
    if session.get('admin_logged_in'):
        user_identifier = session.get('admin_username', 'admin')
        user_name = session.get('admin_username', 'L&D Admin')
    else:
        user_identifier = session.get('learner_global_id') or str(session.get('learner_id', 'learner'))
        user_name = session.get('learner_name', 'Learner')

    # 4. Map user's current reactions & summary counts per post
    posts_data = []
    for p in posts:
        rxns = p.reactions
        counts = {'like': 0, 'love': 0, 'celebrate': 0, 'clap': 0, 'fire': 0}
        user_reaction = None
        
        for r in rxns:
            counts[r.reaction_type] = counts.get(r.reaction_type, 0) + 1
            if r.user_identifier == user_identifier:
                user_reaction = r.reaction_type

        posts_data.append({
            'post': p,
            'counts': counts,
            'total_reactions': len(rxns),
            'user_reaction': user_reaction
        })

    return render_template(
        'learning_wall/index.html',
        posts_data=posts_data,
        user_identifier=user_identifier,
        user_name=user_name
    )


@learning_wall_bp.route('/react', methods=['POST'])
def react():
    """
    AJAX endpoint for toggling reactions on a Learning Wall post.
    Body JSON or Form: { 'post_id': 1, 'reaction_type': 'like' / 'love' / 'celebrate' / 'clap' / 'fire' }
    """
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form

    post_id = data.get('post_id')
    reaction_type = data.get('reaction_type', 'like').lower()

    valid_reactions = ['like', 'love', 'celebrate', 'clap', 'fire']
    if reaction_type not in valid_reactions:
        return jsonify({'success': False, 'message': 'Invalid reaction type.'}), 400

    user_identifier = session.get('learner_global_id') or (session.get('admin_username') if session.get('admin_logged_in') else None)
    user_name = session.get('learner_name') or (session.get('admin_username') if session.get('admin_logged_in') else None)

    if not user_identifier:
        return jsonify({'success': False, 'message': 'Please log in to react to posts.'}), 401

    res = toggle_post_reaction(post_id, user_identifier, user_name, reaction_type)
    return jsonify(res)


@learning_wall_bp.route('/clear', methods=['POST', 'GET'])
def clear_wall():
    """
    Endpoint to clear all events from the Learning Wall.
    Admin restriction checked.
    """
    if not session.get('admin_logged_in'):
        flash("Only L&D Administrators can clear Learning Wall events.", "danger")
        return redirect(url_for('learning_wall.index'))

    clear_all_wall_posts()
    flash("All events have been removed from the Learning Wall.", "success")
    return redirect(url_for('learning_wall.index'))
