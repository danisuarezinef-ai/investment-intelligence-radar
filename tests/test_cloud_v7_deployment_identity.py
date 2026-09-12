import cloud_service_v7 as v7


def test_deployment_identity_is_non_secret_and_fail_closed(monkeypatch):
    monkeypatch.setenv('RAILWAY_GIT_COMMIT_SHA','a'*40)
    monkeypatch.setenv('RAILWAY_SERVICE_ID','svc-test')
    monkeypatch.setenv('RAILWAY_ENVIRONMENT_NAME','production')
    out=v7.deployment_identity()
    assert out['status']=='OBSERVED'
    assert out['deployed_sha']=='a'*40
    assert out['source']=='RAILWAY_GIT_COMMIT_SHA'
    assert out['setup_allowed'] is False
    assert out['can_trade'] is False
    assert out['real_trading'] is False
    assert not any('TOKEN' in str(k).upper() or 'SECRET' in str(k).upper() for k in out)


def test_missing_deployment_identity_never_becomes_verified(monkeypatch):
    monkeypatch.delenv('RAILWAY_GIT_COMMIT_SHA',raising=False)
    monkeypatch.delenv('RADAR_DEPLOY_REV',raising=False)
    out=v7.deployment_identity()
    assert out['status']=='NOT_VERIFIED'
    assert out['deployed_sha'] is None
    assert out['real_trading'] is False
