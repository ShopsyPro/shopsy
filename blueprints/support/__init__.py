from flask import Blueprint

support = Blueprint('support', __name__, url_prefix='/support')

from . import routes 