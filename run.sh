ps -ef|grep 8000|grep -v grep |awk '{print $2}'|xargs kill -9
gunicorn -w 32 -k gevent -b 0.0.0.0:8000 app:app &

