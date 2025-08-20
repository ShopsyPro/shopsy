from flask import render_template
from . import terms

@terms.route('/terms')
def service():
    return render_template('_base/terms.html') 