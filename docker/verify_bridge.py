"""Read-only protocol guard checks inside the app network namespace; no inference."""
import json
import urllib.error
import urllib.request

BASE = 'http://127.0.0.1:11434'
MODEL = 'qwen3:4b-instruct'
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def check(name, path, expected, payload=None, method=None):
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(BASE + path, data=data, method=method,
                                     headers={'Content-Type': 'application/json'})
    try:
        with opener.open(request, timeout=10) as response:
            status, body = response.status, json.load(response)
    except urllib.error.HTTPError as error:
        status, body = error.code, json.load(error)
    assert status == expected, (name, status, expected)
    if name == 'pinned_inventory':
        assert len(body['models']) == 1 and body['models'][0]['name'] == MODEL
        assert body['models'][0]['digest'] == '0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0'
    print(json.dumps({'scenario': name, 'status': 'PASS', 'http_status': status}), flush=True)


if __name__ == '__main__':
    valid = {'model': MODEL, 'stream': False, 'messages': [{'role': 'user', 'content': 'synthetic'}],
             'options': {'num_predict': 8}}
    check('pinned_inventory', '/api/tags', 200)
    check('forbid_model_pull', '/api/pull', 404, {})
    check('forbid_absolute_proxy', '/http://example.invalid/', 404)
    check('forbid_delete', '/api/chat', 405, {}, 'DELETE')
    for name, payload in (
        ('forbid_other_model', {**valid, 'model': 'other'}),
        ('forbid_stream', {**valid, 'stream': True}),
        ('forbid_tools', {**valid, 'tools': []}),
        ('forbid_remote_images', {**valid, 'messages': [{'role': 'user', 'content': 'synthetic', 'images': ['http://example.invalid/']}]}),
        ('forbid_unbounded_output', {**valid, 'options': {'num_predict': 100000}}),
        ('forbid_unbounded_context', {**valid, 'options': {'num_predict': 8, 'num_ctx': 32768}}),
    ):
        check(name, '/api/chat', 422, payload)
    check('forbid_large_body', '/api/chat', 413, {'padding': 'x' * 131072})
