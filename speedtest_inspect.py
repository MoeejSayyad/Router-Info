import inspect
import speedtest

print('download sig:', inspect.signature(speedtest.Speedtest.download))
print('upload sig:  ', inspect.signature(speedtest.Speedtest.upload))
print('best sig:    ', inspect.signature(speedtest.Speedtest.get_best_server))
print('results attr:', hasattr(speedtest.Speedtest, 'results'))
print('results type:', type(getattr(speedtest.Speedtest, 'results', None)))
print('results repr:', getattr(speedtest.Speedtest, 'results', None))
