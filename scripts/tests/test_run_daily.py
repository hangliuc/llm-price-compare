from unittest.mock import patch


@patch("scripts.run_daily.pipeline_main", return_value=0)
def test_legacy_run_daily_delegates_to_pipeline(mock_main):
    from scripts.run_daily import main

    assert main() == 0
    mock_main.assert_called_once_with(["run"])
