from types import SimpleNamespace
import pytest
from scripts import local_action

@pytest.mark.parametrize('service', ['postgres', 'redis', 'monitoring-agent', 'payment-service; echo injected'])
def test_disallows_non_application_services(service):
    with pytest.raises(ValueError):
        local_action.command('restart', service)

@pytest.mark.parametrize('lines', [0,501,-1,True])
def test_bounds_log_output(lines):
    with pytest.raises(ValueError):
        local_action.command('logs','payment-service',lines)


def test_restart_requires_explicit_flag(monkeypatch):
    calls=[]
    monkeypatch.setattr(local_action.subprocess,'run',lambda *a,**k: calls.append(a))
    with pytest.raises(SystemExit):
        local_action.main(['restart','payment-service'])
    assert calls == []


def test_remote_engine_rejected(monkeypatch):
    monkeypatch.delenv('DOCKER_HOST',raising=False)
    monkeypatch.delenv('DOCKER_CONTEXT',raising=False)
    monkeypatch.setattr(local_action.subprocess,'run',lambda *a,**k: SimpleNamespace(stdout='ssh://remote-host'))
    with pytest.raises(ValueError):
        local_action.require_local_engine()


def test_host_override_rejected_before_execution(monkeypatch):
    monkeypatch.setenv('DOCKER_HOST','tcp://remote:2375')
    calls=[]
    monkeypatch.setattr(local_action.subprocess,'run',lambda *a,**k: calls.append(a))
    with pytest.raises(ValueError):
        local_action.require_local_engine()
    assert calls == []


def test_local_restart_is_exact_argv_without_shell(monkeypatch):
    monkeypatch.delenv('DOCKER_HOST',raising=False)
    monkeypatch.delenv('DOCKER_CONTEXT',raising=False)
    calls=[]
    def run(argv,**kwargs):
        calls.append((argv,kwargs))
        return SimpleNamespace(stdout='npipe:////./pipe/dockerDesktopLinuxEngine')
    monkeypatch.setattr(local_action.subprocess,'run',run)
    assert local_action.main(['restart','payment-service','--confirm-restart']) == 0
    assert calls[-1][0][-5:] == ['restart','--no-deps','-t','10','payment-service']
    assert all(not kwargs.get('shell',False) for _,kwargs in calls)


def test_logs_use_fixed_compose_path_and_bounded_tail():
    cmd=local_action.command('logs','order-service',25)
    assert cmd[3] == str(local_action.ROOT/'docker-compose.yml')
    assert cmd[-5:] == ['logs','--no-color','--tail','25','order-service']
