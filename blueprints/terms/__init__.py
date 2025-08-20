from flask import Blueprint

terms = Blueprint('terms', __name__)

from . import routes 