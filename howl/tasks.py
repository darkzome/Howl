import json
import os
from config import es, whatwebdb

import ipaddress
import redis
from celery import Celery, platforms
from celery.schedules import crontab

platforms.C_FORCE_ROOT = True
app = Celery('tasks', broker='redis://localhost:6379/1')
ip_db = redis.Redis(host='localhost', port=6379, db=2, decode_responses=True)


@app.task
def add2whatweb(target_path, port):
    logfile = '{}_{}.json'.format(target_path, port)
    if os.path.exists(logfile):
        os.system('rm {}'.format(logfile))
    os.system(
        "whatweb --no-errors -t 255 -i {} --url-suffix=':{}' --log-json={}".
        format(target_path, port, logfile))
    with open(logfile, 'r') as logf:
        lines = json.load(logf)
        for target in lines:
            save2es.delay(target)
    whatwebdb.decr('scanning')
    if os.path.exists(logfile):
        os.remove(logfile)


@app.task
def save2es(target):
    try:
        parse_target = target['target'].split(':')
        if len(parse_target) > 2:
            target['port'] = parse_target[-1].split('/')[0]
        else:
            target['port'] = '80'
        es.index(
            index='whatweb',
            doc_type="detail",
            id=int(
                str(
                    int(
                        ipaddress.IPv4Address(target['plugins']['IP']['string']
                                              [0]))) + target['port']),
            body=target)
        print(target)
    except:
        pass

@app.task
def masscan(target, port):
    whatwebdb.incr('scanning')
    result_path = '/tmp/tmp_{}_{}'.format(target.replace('/', '_'),port)
    results = os.popen(
        'masscan -p{0} {1} --rate=500 -oL {2} && cat {2}'.format(
            port, target, result_path)).read().split('\n')[1:-2]
    os.system('rm {}'.format(result_path))
    for result in results:
        print(result)
        ip = result.split(" ")[3]
        ip_db.sadd('{}_{}'.format(target, port), ip)
    target_path = result_path + '.txt'
    os.system('rm {}'.format(target_path))
    with open(target_path, 'a+') as f:
        for i in ip_db.smembers(target):
            f.writelines(i + '\n')
    if len(ip_db.smembers('{}_{}'.format(target, port))):
        add2whatweb.delay(target_path, port)
    else:
        whatwebdb.decr('scanning')