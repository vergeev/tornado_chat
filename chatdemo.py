# -*- coding: UTF-8 -*-

import asyncio
import os
import uuid

from tornado import escape, ioloop, locks, web
from tornado.options import define, options, parse_command_line

define('port', default=8888, help='run on the given port', type=int)  # noqa: Z432
define('debug', default=True, help='run in debug mode')


class MessageBuffer(object):

    def __init__(self):
        # cond is notified whenever the message cache is updated
        self.cond = locks.Condition()
        self.cache = []
        self.cache_size = 200

    def get_messages_since(self, cursor):
        """Returns a list of messages newer than the given cursor.

        ``cursor`` should be the ``id`` of the last message received.
        """
        messages = []
        for msg in reversed(self.cache):
            if cursor == msg['id']:
                break
            messages.append(msg)
        messages.reverse()
        return messages

    def add_message(self, message):
        self.cache.append(message)
        if len(self.cache) > self.cache_size:
            self.cache = self.cache[-self.cache_size:]
        self.cond.notify_all()


# Making this a non-singleton is left as an exercise for the reader.
global_message_buffer = MessageBuffer()


class MainHandler(web.RequestHandler):
    def get(self):
        self.render('index.html', messages=global_message_buffer.cache)


class MessageNewHandler(web.RequestHandler):
    """Post a new message to the chat room."""

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
        global_message_buffer.add_message(message)


class MessageUpdatesHandler(web.RequestHandler):
    """Long-polling request for new messages.

    Waits until new messages are available before returning anything.
    """

    async def post(self):
        cursor = self.get_argument('cursor', None)
        messages = global_message_buffer.get_messages_since(cursor)
        while not messages:
            # Save the Future returned here so we can cancel it in
            # on_connection_close.
            self.wait_future = global_message_buffer.cond.wait()
            try:
                await self.wait_future
            except asyncio.CancelledError:
                return
            messages = global_message_buffer.get_messages_since(cursor)
        if self.request.connection.stream.closed():
            return
        self.write({'messages': messages})

    def on_connection_close(self):
        self.wait_future.cancel()


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
