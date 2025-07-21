# Standard library imports
import logging
import os
from logging.handlers import RotatingFileHandler

# Third-party imports
from flask import Flask, render_template, redirect, url_for, flash, request
from flask_login import LoginManager, current_user
from flask_sqlalchemy import SQLAlchemy
from flask_apscheduler import APScheduler
from flask_caching import Cache
from sqlalchemy.exc import OperationalError, DisconnectionError

# psycopg3 uses binary implementation automatically

# Local imports
from .config import Config
from .models import db, User

login_manager = LoginManager()

scheduler = APScheduler()

cache = Cache()


@login_manager.user_loader
def load_user(user_id):
    """Flask-Login user loader"""
    try:
        return User.query.get(user_id)
    except (OperationalError, DisconnectionError) as e:
        # Log on database connection error
        logger = logging.getLogger(__name__)
        logger.error(f"Database connection error (user loading): {e}")
        return None
    except Exception as e:
        # Handle other exceptions
        logger = logging.getLogger(__name__)
        logger.error(f"User loading error: {e}")
        return None


def create_app(config_class=Config, testing=False):
    """CleanBox Flask application factory"""

    app = Flask(__name__)
    app.config.from_object(config_class)
    if testing:
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False  # Disable CSRF for testing if needed

    # Logging setup
    if not app.debug and not app.testing:
        if not os.path.exists("logs"):
            os.mkdir("logs")
        file_handler = RotatingFileHandler(
            "logs/cleanbox.log", maxBytes=10240, backupCount=10
        )
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]"
            )
        )
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)

        app.logger.setLevel(logging.INFO)
        app.logger.info("CleanBox started")

    # Initialize database
    db.init_app(app)

    # Initialize login manager
    login_manager.init_app(app)

    # Initialize scheduler (skip in test environment)
    if not testing:
        scheduler.init_app(app)
        scheduler.start()

        # Register 30-min interval webhook monitoring job
        from .email.routes import monitor_and_renew_webhooks

        def scheduled_webhook_monitoring():
            with app.app_context():
                monitor_and_renew_webhooks()

        scheduler.add_job(
            id="webhook_monitor",
            func=scheduled_webhook_monitoring,
            trigger="interval",
            minutes=30,
            replace_existing=True,
        )

    # Initialize cache
    cache.init_app(app)

    # Register blueprints
    from .auth.routes import auth_bp
    from .main.routes import main_bp
    from .category.routes import category_bp
    from .email.routes import email_bp
    from .email.webhook_routes import webhook_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(main_bp, url_prefix="/main")
    app.register_blueprint(category_bp, url_prefix="/category")
    app.register_blueprint(email_bp, url_prefix="/email")
    app.register_blueprint(webhook_bp, url_prefix="/webhook")

    # Main route (root URL)
    @app.route("/")
    def index():
        # Redirect logged-in users to dashboard
        if current_user and current_user.is_authenticated:
            return redirect(url_for("main.dashboard"))

        # Show landing page for non-logged-in users
        return render_template("landing.html")

    # home endpoint
    @app.route("/home")
    def home():
        return redirect(url_for("main.dashboard"))

    # Unauthorized error handler
    @app.errorhandler(401)
    def unauthorized(error):
        if current_user and current_user.is_authenticated:
            # Logged-in user but no permission
            flash("You do not have permission for this feature.", "error")
            return redirect(url_for("main.dashboard"))
        else:
            # Not logged in
            flash("Login required.", "error")
            return redirect(url_for("auth.login"))

    @app.errorhandler(403)
    def forbidden(error):
        flash("You do not have access rights to this feature.", "error")
        return redirect(url_for("main.dashboard"))

    # Initialize database (only if not testing)
    if not app.config.get("TESTING", False):
        with app.app_context():
            db.create_all()

    return app


def init_db(app):
    """Initialize database"""
    with app.app_context():
        db.create_all()
        print("CleanBox database initialized.")
