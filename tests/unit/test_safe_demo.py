import subprocess
from unittest.mock import Mock
import pytest
from scripts import safe_demo as demo

@pytest.fixture(autouse=True)
def isolated_state(tmp_path,monkeypatch):
    monkeypatch.setattr(demo,'STATE_DIR',tmp_path)

@pytest.mark.parametrize('service',['postgres','redis','monitoring-agent','payment-service; bad'])
def test_demo_rejects_non_application_targets(service):
    with pytest.raises(ValueError):demo.compose('stop',service)

@pytest.mark.parametrize('seconds',[0,29,61,600])
def test_duration_is_bounded(seconds):
    with pytest.raises(ValueError):demo.start('payment-service',seconds)


def test_fixed_compose_command(monkeypatch):
    run=Mock();monkeypatch.setattr(demo.subprocess,'run',run)
    demo.compose('stop','payment-service')
    args=run.call_args.args[0]
    assert args[-4:]==['stop','--timeout','1','payment-service']
    assert 'shell' not in run.call_args.kwargs


def test_watchdog_restores_expired_demo(monkeypatch):
    demo.write_state('payment-service',{'run_id':'demo','deadline':0,'restored':False})
    monkeypatch.setattr(demo,'require_local_engine',lambda:None)
    compose=Mock();monkeypatch.setattr(demo,'compose',compose)
    demo.watchdog('payment-service','demo')
    compose.assert_called_once_with('start','payment-service')
    assert demo.read_state('payment-service')['restored']


def test_old_watchdog_cannot_restore_new_demo(monkeypatch):
    demo.write_state('payment-service',{'run_id':'new','deadline':0,'restored':False})
    compose=Mock();monkeypatch.setattr(demo,'compose',compose)
    demo.watchdog('payment-service','old')
    compose.assert_not_called()


def test_restore_cancels_timer_and_is_idempotent(monkeypatch):
    demo.write_state('payment-service',{'run_id':'demo','deadline':9999999999,'restored':False})
    compose=Mock();monkeypatch.setattr(demo,'compose',compose)
    demo.restore('payment-service')
    assert demo.restore('payment-service','demo') is False
    compose.assert_called_once_with('start','payment-service')


def test_restore_runs_when_stop_raises(monkeypatch):
    monkeypatch.setattr(demo,'require_local_engine',lambda:None)
    monkeypatch.setattr(demo.subprocess,'run',Mock(return_value=Mock(stdout='true healthy')))
    def spawn(service,run_id):
        state=demo.read_state(service);state['watchdog_ready']=True;demo.write_state(service,state)
        return Mock()
    monkeypatch.setattr(demo,'spawn_watchdog',spawn)
    compose=Mock(side_effect=[subprocess.TimeoutExpired('docker',20),None])
    monkeypatch.setattr(demo,'compose',compose)
    with pytest.raises(subprocess.TimeoutExpired):demo.start('payment-service')
    assert [c.args[0] for c in compose.call_args_list]==['stop','start']
    assert demo.read_state('payment-service')['restored']


def test_missing_watchdog_prevents_failure_injection(monkeypatch):
    monkeypatch.setattr(demo,'require_local_engine',lambda:None)
    monkeypatch.setattr(demo.subprocess,'run',Mock(return_value=Mock(stdout='true healthy')))
    monkeypatch.setattr(demo,'spawn_watchdog',lambda *a:Mock(poll=lambda:1))
    compose=Mock();monkeypatch.setattr(demo,'compose',compose)
    with pytest.raises(RuntimeError):demo.start('payment-service')
    compose.assert_called_once_with('start','payment-service')
