# One worker preserves SQLite and process-local inference serialization semantics.
bind = '0.0.0.0:8766'  # Container interface only; Compose host publication is 127.0.0.1.
workers = 1
worker_class = 'gthread'
threads = 4
timeout = 240
graceful_timeout = 30
keepalive = 2
accesslog = None
errorlog = '-'
loglevel = 'info'
control_socket_disable = True  # No control socket in the non-root user's nonexistent home.
forwarded_allow_ips = '127.0.0.1,::1'
