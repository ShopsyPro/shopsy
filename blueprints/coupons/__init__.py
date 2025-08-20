from flask import Blueprint

coupons_bp = Blueprint('coupons', __name__)

from . import routes
