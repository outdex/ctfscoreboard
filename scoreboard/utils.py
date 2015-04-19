# Copyright 2014 David Tomaschik <david@systemoverlord.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
import errors
import flask
import functools
import hashlib
import hmac
import os
import pytz
import urlparse

from scoreboard.app import app

# Use dateutil if available
try:
    from dateutil import parser as dateutil
except ImportError:
    dateutil = None


def login_required(f):
    """Decorator to require login for a method."""

    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if not flask.g.user:
            raise errors.AccessDeniedError('You must be logged in.')
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    """Decorator to require admin for a method."""

    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        try:
            if not flask.g.user.admin:
                flask.abort(403)
        except AttributeError:
            flask.abort(403)
        return f(*args, **kwargs)
    return login_required(wrapper)


def team_required(f):
    """Require that they are a member of a team."""

    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if not flask.g.team:
            app.logger.warning(
                'Team request received for player without team.')
            flask.abort(400)
        return f(*args, **kwargs)
    return login_required(wrapper)


def is_admin():
    """Check if current user is an admin."""
    try:
        return flask.g.user.admin
    except:
        return False


def get_required_field(name, verbose_name=None):
    """Retrieve a field or raise an error."""

    try:
        return flask.request.form[name]
    except KeyError:
        verbose_name = verbose_name or name
        raise errors.ValidationError('%s is a required field.' % verbose_name)


def parse_bool(b):
    b = b.lower()
    return b in ('true', '1')


def access_team(team):
    """Check permission to team."""

    if flask.g.user and flask.g.user.admin:
        return True
    try:
        team = team.tid
    except AttributeError:
        pass
    if flask.g.team and flask.g.team.tid == team:
        return True
    return False


def attachment_dir(create=False):
    """Return path to attachment dir."""

    config_dir = app.config.get('ATTACHMENT_DIR', 'attachments')
    if app.config.get('CWD'):
        target_dir = os.path.normpath(os.path.join(app.config.get('CWD'),
            config_dir))
    else:
        target_dir = os.path.abspath(config_dir)
    if not os.path.isdir(target_dir):
        if create:
            os.mkdir(target_dir)
        else:
            app.logger.error('Missing or invalid ATTACHMENT_DIR: %s', target_dir)
            flask.abort(500)
    return target_dir


def compare_digest(a, b):
    """Intended to be a constant-time comparison."""
    if hasattr(hmac, 'compare_digest'):
        return hmac.compare_digest(a, b)
    return hashlib.sha1(a).digest() == hashlib.sha1(b).digest()


def absolute_url(path):
    """Build an absolute URL.  Not safe for untrusted input."""
    return urlparse.urljoin(flask.request.host_url, path)


class GameTime(object):
    """Manage start/end times for the game."""

    @classmethod
    def setup(cls):
        """Get start and end time."""
        cls.start, cls.end = app.config.get('GAME_TIME', (None, None))
        if isinstance(cls.start, basestring):
            cls.start = cls._parsedate(cls.start)
        if isinstance(cls.end, basestring):
            cls.end = cls._parsedate(cls.end)

    @classmethod
    def countdown(cls, end=False):
        """Time remaining to start or end."""
        until = cls.end if end else cls.start
        if until is None:
            return None
        return until - datetime.datetime.utcnow()

    @classmethod
    def state(cls):
        now = datetime.datetime.utcnow()
        if cls.start and cls.start > now:
            return 'BEFORE'
        if cls.end and cls.end < now:
            return 'AFTER'
        return 'DURING'

    @classmethod
    def open(cls, after_end=False):
        """Is the game open?  If after_end, keeps open."""
        state = cls.state()
        if state == 'DURING' or (after_end and state == 'AFTER'):
            return True
        return False

    @classmethod
    def require_open(cls, f, after_end=False, or_admin=True):
        """Decorator for requiring the game is open."""
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            if (cls.open(after_end) or
                    (or_admin and flask.g.user and flask.g.user.admin)):
                return f(*args, **kwargs)
            raise errors.AccessDeniedError(cls.message())
        return wrapper

    @classmethod
    def message(cls):
        state = cls.state()
        if state == 'BEFORE':
            return 'Game begins in %s.' % str(cls.countdown())
        if state == 'AFTER':
            return 'Game is over.'
        return '%s left in the game.' % str(cls.countdown(end=True))

    @staticmethod
    def _parsedate(datestr):
        """Return a UTC non-TZ-aware datetime from a string."""
        if dateutil:
            dt = dateutil.parse(datestr)
            if dt.tzinfo:
                dt = dt.astimezone(pytz.UTC).replace(tzinfo=None)
            return dt
        # TODO: parse with strptime
        raise RuntimeError('No parser available.')

GameTime.setup()
require_gametime = GameTime.require_open