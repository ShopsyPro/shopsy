from flask import Blueprint

superadmin_bp = Blueprint('superadmin', __name__, url_prefix='/superadmin')

from . import routes 