from unittest.mock import Mock
import os
import pytest
import demo

@pytest.mark.parametrize('enabled',[False,True])
def test_compose_demo_flag_is_explicit_and_does_not_mutate_environment(monkeypatch,enabled):
    monkeypatch.delenv('SENTINEL_DEMO_ENABLED',raising=False)
    run=Mock();monkeypatch.setattr(demo.subprocess,'run',run)
    demo.compose('up','-d','--no-deps','payment-service',demo_enabled=enabled)
    passed=run.call_args.kwargs['env']
    assert passed.get('SENTINEL_DEMO_ENABLED')==('1' if enabled else None)
    assert 'SENTINEL_DEMO_ENABLED' not in os.environ
    assert run.call_args.args[0][-1]=='payment-service'
