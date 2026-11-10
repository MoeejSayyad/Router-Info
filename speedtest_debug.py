import speedtest

print('speedtest version', getattr(speedtest, '__version__', 'unknown'))
print('starting')
try:
    st = speedtest.Speedtest(secure=True)
    print('created Speedtest object')
    print('initial results attribute exists?', hasattr(st, 'results'))
    print('initial results', getattr(st, 'results', None))
    server = st.get_best_server()
    print('best server', server)
    print('after get_best_server results', getattr(st, 'results', None))
    d = st.download()
    print('download bits', d)
    print('after download results', getattr(st, 'results', None))
    u = st.upload()
    print('upload bits', u)
    print('after upload results', getattr(st, 'results', None))
    print('final ping', getattr(st, 'results', {}).get('ping'))
except Exception as e:
    import traceback
    traceback.print_exc()
