from unittest.mock import Mock, patch

from export_service import InfraiClient, OrderHandoff, generate_download, render_export


def test_handoff_export_has_business_state_and_signed_download():
        rows = [OrderHandoff("o1", "s1", "b@example.com", "10.00", "handed_off")]
        client = Mock(spec=InfraiClient)
        client.presign.side_effect = [{"url": "https://upload"}, {"url": "https://download"}]
        with patch("export_service.urllib.request.urlopen") as opened:
            opened.return_value.__enter__.return_value.status = 200
            result = generate_download(rows, client)
        assert result == "https://download"
        assert "handed_off" in render_export(rows).decode()
        client.bucket_create.assert_called_once_with("marketplace-exports")
        assert client.presign.call_args_list[0].args == ("marketplace-exports", "orders/export.csv", "put")
