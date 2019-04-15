# -*- coding: UTF-8 -*-

import os
import queries
import uuid

from tornado import escape, ioloop, gen, web
from tornado.options import define, options, parse_command_line

define('port', default=8888, help='run on the given port', type=int)  # noqa: Z432
define('debug', default=True, help='run in debug mode')


class MainHandler(web.RequestHandler):

    def initialize(self):
        self.session = queries.TornadoSession(
            os.environ.get('DATABASE_URL')
        )

    @gen.coroutine
    def get(self):
        results = yield self.session.query(
            'SELECT uuid as id, body, html FROM messages;',
        )
        messages = results.items()
        results.free()
        self.render('index.html', messages=messages)


class MessageNewHandler(web.RequestHandler):
    """Post a new message to the chat room."""

    def initialize(self):
        self.session = queries.TornadoSession(
            os.environ.get('DATABASE_URL')
        )

    @gen.coroutine
    def post(self):
        message = {'id': str(uuid.uuid4()), 'body': self.get_argument('body')}
        # render_string() returns a byte string, which is not supported
        # in json, so we must convert it to a character string.
        message['html'] = escape.to_unicode(
            self.render_string('message.html', message=message),
        )
        if self.get_argument('next', None):
            self.redirect(self.get_argument('next'))
        else:
            self.write(message)
        try:
            results = yield self.session.query(
                'INSERT INTO messages (uuid, body, html) VALUES (%s, %s, %s);',
                [message['id'], message['body'], message['html']]
            )

            results.free()
        except (queries.DataError,
                queries.IntegrityError) as error:
            self.set_status(409)
            self.finish({'error': {'error': error.pgerror.split('\n')[0][8:]}})


class MessageUpdatesHandler(web.RequestHandler):
    """Long-polling request for new messages.

    Waits until new messages are available before returning anything.
    """

    def initialize(self):
        self.session = queries.TornadoSession(
            os.environ.get('DATABASE_URL')
        )

    @gen.coroutine
    def post(self):
        cursor = self.get_argument('cursor', None)
        if cursor:
            self.results = yield self.session.query(
                'SELECT uuid as id, body, html FROM messages'
                ' WHERE id > (SELECT id FROM messages WHERE uuid=%s LIMIT 1);',
                [cursor]
            )
        else:
            self.results = yield self.session.query(
                'SELECT uuid as id, body, html FROM messages;'
            )
        if self.results:
            messages = [
                {
                    'id': str(result['id']),
                    'body': result['body'],
                    'html': result['html'],
                }
                for result in self.results
            ]
            print({'messages': messages})
            self.finish({'messages': messages})
        self.results.free()

    def on_connection_close(self):
        # if self.results:
        self.results.free()


def main():
    parse_command_line()
    app = web.Application(
        [
            (r'/', MainHandler),
            (r'/a/message/new', MessageNewHandler),
            (r'/a/message/updates', MessageUpdatesHandler),
        ],
        cookie_secret='__TODO:_GENERATE_YOUR_OWN_RANDOM_VALUE_HERE__',
        template_path=os.path.join(os.path.dirname(__file__), 'templates'),
        static_path=os.path.join(os.path.dirname(__file__), 'static'),
        xsrf_cookies=True,
        debug=options.debug,
    )
    app.listen(options.port)
    ioloop.IOLoop.current().start()


if __name__ == '__main__':
    main()
