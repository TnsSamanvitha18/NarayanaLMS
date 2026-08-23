import datetime
from app.models import db
from app.models.user import Learner
from app.models.course import Course
from app.models.enrollment import LearnerEnrollment
from app.models.learning_wall import LearningWallPost, LearningWallReaction

def create_completion_post(learner_id, course_id, final_score=None):
    """
    Automated trigger: Generates a system news-bulletin post when a learner completes a course.
    """
    learner = Learner.query.get(learner_id)
    course = Course.query.get(course_id)
    if not learner or not course:
        return None

    # Check if a post for this learner & course completion already exists
    existing = LearningWallPost.query.filter_by(
        post_type='COURSE_COMPLETION',
        learner_id=learner_id,
        course_id=course_id
    ).first()
    if existing:
        return existing

    score_str = f" with a score of {final_score:.1f}%" if final_score is not None else ""
    title = f"🎓 Course Completion: {learner.name}"
    content = f"🎉 **{learner.name}** ({learner.department or 'Learner'}) has successfully completed the course **{course.name}**{score_str}! Congratulations on this achievement!"

    post = LearningWallPost(
        post_type='COURSE_COMPLETION',
        title=title,
        content=content,
        learner_id=learner.id,
        course_id=course.id,
        icon='fa-trophy',
        badge_color='bg-success-subtle text-success border-success-subtle'
    )
    db.session.add(post)
    db.session.commit()
    return post


def check_and_generate_birthday_posts():
    """
    Automated trigger: Checks for learners with birthdays today and generates system birthday bulletin posts.
    """
    today = datetime.date.today()
    learners = Learner.query.filter(Learner.date_of_birth.isnot(None)).all()
    created_posts = []

    for l in learners:
        if l.date_of_birth and l.date_of_birth.month == today.month and l.date_of_birth.day == today.day:
            # Check if birthday post for this learner was already created today
            start_of_day = datetime.datetime.combine(today, datetime.time.min)
            existing = LearningWallPost.query.filter(
                LearningWallPost.post_type == 'BIRTHDAY',
                LearningWallPost.learner_id == l.id,
                LearningWallPost.created_at >= start_of_day
            ).first()

            if not existing:
                title = f"🎂 Happy Birthday, {l.name}!"
                content = f"🎈 Wishing **{l.name}** ({l.department or 'Team'}) a very Happy Birthday! May your day be filled with joy and your year with continuous learning and success!"
                post = LearningWallPost(
                    post_type='BIRTHDAY',
                    title=title,
                    content=content,
                    learner_id=l.id,
                    icon='fa-cake-candles',
                    badge_color='bg-warning-subtle text-warning border-warning-subtle'
                )
                db.session.add(post)
                created_posts.append(post)

    if created_posts:
        db.session.commit()
    return created_posts


def seed_sample_wall_posts_if_empty():
    """
    Checks for completed enrollments or today's birthdays to generate real posts if empty.
    Does not auto-generate artificial sample posts.
    """
    if LearningWallPost.query.count() > 0:
        return

    # 1. First, check if there are actual completed enrollments and generate real posts
    completed_enrollments = LearnerEnrollment.query.filter_by(completion_status='Completed').all()
    for en in completed_enrollments:
        create_completion_post(en.learner_id, en.course_id, final_score=en.final_score)

    # 2. Check and generate birthday posts for learners whose birthday is today
    check_and_generate_birthday_posts()


def clear_all_wall_posts():
    """
    Deletes all posts and reactions from the Learning Wall.
    """
    LearningWallReaction.query.delete()
    LearningWallPost.query.delete()
    db.session.commit()
    return True


def toggle_post_reaction(post_id, user_identifier, user_name, reaction_type):
    """
    Toggles a reaction for a post. If the exact same reaction exists, it is removed (untoggled).
    If a different reaction exists, it is updated to the new reaction type.
    """
    post = LearningWallPost.query.get_or_404(post_id)
    
    existing = LearningWallReaction.query.filter_by(
        post_id=post.id,
        user_identifier=user_identifier
    ).first()

    if existing:
        if existing.reaction_type == reaction_type:
            # Toggle off
            db.session.delete(existing)
            action = 'removed'
        else:
            # Change reaction
            existing.reaction_type = reaction_type
            action = 'updated'
    else:
        # Add new reaction
        new_rxn = LearningWallReaction(
            post_id=post.id,
            user_identifier=user_identifier,
            user_name=user_name,
            reaction_type=reaction_type
        )
        db.session.add(new_rxn)
        action = 'added'

    db.session.commit()
    
    # Calculate updated reaction summary counts
    rxns = LearningWallReaction.query.filter_by(post_id=post.id).all()
    counts = {'like': 0, 'love': 0, 'celebrate': 0, 'clap': 0, 'fire': 0}
    user_reaction = None
    
    for r in rxns:
        counts[r.reaction_type] = counts.get(r.reaction_type, 0) + 1
        if r.user_identifier == user_identifier:
            user_reaction = r.reaction_type

    return {
        'success': True,
        'action': action,
        'post_id': post.id,
        'counts': counts,
        'total_reactions': len(rxns),
        'user_reaction': user_reaction
    }
