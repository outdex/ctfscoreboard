
import functools
import json
import flask

from werkzeug.contrib import cache

from scoreboard import app


class CacheWrapper(object):

    def __init__(self, app):
        cache_type = app.config.get('CACHE_TYPE')
        if cache_type == 'memcached':
            host = app.config['MEMCACHE_HOST']
            self._cache = cache.MemcachedCache([host])
        elif cache_type == 'appengine':
            self._cache = cache.MemcachedCache()
        elif cache_type == 'local':
            self._cache = cache.SimpleCache()
        else:
            self._cache = cache.NullCache()

    def __getattr__(self, name):
        return getattr(self._cache, name)


global_cache = CacheWrapper(app)


def rest_cache(f, cache_key=None):
    """Mark a function for global caching."""
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        if not cache_key:
            try:
                cache_key = '%s/%s' % (
                        f.im_class.__name__, f.__name__)
            except AttributeError:
                cache_key = f.__name__
        return _rest_cache_caller(f, cache_key, *args, **kwargs)
    return wrapped


def rest_team_cache(f, name=None):
    """Mark a function for per-team caching."""
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        cache_key = None
        if flask.g.team:
            if name:
                cache_key = name % (flask.g.team.tid)
            else:
                try:
                    cache_key = '%s/%s/%s' % (
                            f.im_class.__name__, f.__name__, flask.g.team.tid)
                except AttributeError:
                    cache_key = '%s/%s' % (
                            f.__name__, flask.g.team.tid)
            return _rest_cache_caller(f, cache_key, *args, **kwargs)
        return f(*args, **kwargs)
    return wrapped


def delete(key):
    """Delete cache entry."""
    global_cache.delete(key)


def clear():
    """Flush global cache."""
    global_cache.clear()


def delete_team(base_key):
    """Delete team-based cache entry."""
    if not flask.g.team:
        return
    global_cache.delete(base_key % flask.g.team.tid)


def _rest_cache_caller(f, cache_key, *args, **kwargs):
    value = global_cache.get(cache_key)
    if value:
        try:
            return _rest_add_cache_header(json.loads(value), True)
        except ValueError:
            pass
    value = f(*args, **kwargs)
    try:
        global_cache.set(cache_key, json.dumps(value))
    except TypeError:
        pass
    return _rest_add_cache_header(value)


def _rest_add_cache_header(rv, hit=False):
    headers = {'X-Cache-Hit': str(hit)}
    if isinstance(rv, tuple):
        if len(rv) == 1:
            return (rv[0], 200, headers)
        if len(rv) == 2:
            return (rv[0], rv[1], headers)
        if len(rv) == 3:
            if rv[2] is None:
                return (rv[0], rv[1], headers)
            if isinstance(rv[2], dict):
                rv[2].update(headers)
                return rv
    if isinstance(rv, (list, dict)):
        return rv, 200, headers
    # TODO: might need to support Response objects
    return rv