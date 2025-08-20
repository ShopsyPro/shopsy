from flask import render_template
from . import privacy

@privacy.route('/privacy')
def policy():
    return render_template('_base/privacy.html') 