from flask import Blueprint

category_bp = Blueprint("category", __name__, url_prefix="/category")

from . import routes
