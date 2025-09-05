# Copyright 2015-2016 Yelp Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import json
import re

from mock import Mock
from mock import patch

from paasta_tools.cli.cmds.show_metric_providers import format_instance_info
from paasta_tools.cli.cmds.show_metric_providers import format_metric_provider
from paasta_tools.cli.cmds.show_metric_providers import paasta_show_metric_providers
from paasta_tools.kubernetes_tools import KubernetesDeploymentConfig


def strip_ansi_codes(text):
    """Remove ANSI color codes from text for testing"""
    ansi_escape = re.compile(r"\x1b\[[0-9;]*m")
    return ansi_escape.sub("", text)


class TestFormatMetricProvider:
    def test_format_cpu_provider(self):
        """Test formatting of CPU metric provider"""
        cpu_provider = {
            "type": "cpu",
            "setpoint": 0.8,
            "decision_policy": "proportional",
        }
        result = strip_ansi_codes(format_metric_provider(cpu_provider))

        assert "Type: cpu" in result
        assert "80.0% CPU utilization" in result
        assert "Decision Policy: proportional" in result

    def test_format_uwsgi_provider(self):
        """Test formatting of uWSGI/RPS metric provider"""
        uwsgi_provider = {
            "type": "uwsgi",
            "setpoint": 400,
            "decision_policy": "proportional",
            "desired_active_requests_per_replica": 10,
        }
        result = strip_ansi_codes(format_metric_provider(uwsgi_provider))

        assert "Type: uwsgi" in result
        assert "Setpoint: 400" in result
        assert "Decision Policy: proportional" in result
        assert "Additional Parameters:" in result
        assert "desired_active_requests_per_replica: 10" in result

    def test_format_provider_with_minimal_config(self):
        """Test formatting provider with only required fields"""
        minimal_provider = {"type": "memory"}
        result = strip_ansi_codes(format_metric_provider(minimal_provider))

        assert "Type: memory" in result
        # Should not crash on missing optional fields


class TestFormatInstanceInfo:
    def test_format_autoscaling_disabled(self):
        """Test formatting when autoscaling is disabled"""
        mock_config = Mock(autospec=None)
        mock_config.is_autoscaling_enabled.return_value = False

        result = format_instance_info(
            service="test-service",
            cluster="test-cluster",
            instance="main",
            config=mock_config,
            json_output=False,
        )

        assert result is None

    def test_format_autoscaling_disabled_json(self):
        """Test JSON formatting when autoscaling is disabled"""
        mock_config = Mock(autospec=None)
        mock_config.is_autoscaling_enabled.return_value = False

        result = format_instance_info(
            service="test-service",
            cluster="test-cluster",
            instance="main",
            config=mock_config,
            json_output=True,
        )

        assert result["autoscaling_enabled"] is False
        assert result["service"] == "test-service"
        assert result["cluster"] == "test-cluster"
        assert result["instance"] == "main"

    def test_format_autoscaling_enabled_human_readable(self):
        """Test human-readable formatting when autoscaling is enabled"""
        mock_config = Mock(autospec=None)
        mock_config.is_autoscaling_enabled.return_value = True
        mock_config.get_min_instances.return_value = 2
        mock_config.get_max_instances.return_value = 10
        mock_config.get_autoscaling_params.return_value = {
            "metrics_providers": [
                {"type": "cpu", "setpoint": 0.7, "decision_policy": "proportional"}
            ]
        }

        result = format_instance_info(
            service="test-service",
            cluster="test-cluster",
            instance="main",
            config=mock_config,
            json_output=False,
        )

        output = strip_ansi_codes(result["formatted_output"])
        assert "test-cluster.main" in output
        assert "Min/Max Instances: 2/10" in output
        assert "Metric Providers (1):" in output
        assert "Type: cpu" in output

    def test_format_autoscaling_enabled_json(self):
        """Test JSON formatting when autoscaling is enabled"""
        mock_config = Mock(autospec=None)
        mock_config.is_autoscaling_enabled.return_value = True
        mock_config.get_min_instances.return_value = 2
        mock_config.get_max_instances.return_value = 10
        mock_config.get_autoscaling_params.return_value = {
            "metrics_providers": [
                {"type": "cpu", "setpoint": 0.7, "decision_policy": "proportional"}
            ],
            "setpoint": 0.7,
        }

        result = format_instance_info(
            service="test-service",
            cluster="test-cluster",
            instance="main",
            config=mock_config,
            json_output=True,
        )

        assert result["autoscaling_enabled"] is True
        assert result["service"] == "test-service"
        assert result["cluster"] == "test-cluster"
        assert result["instance"] == "main"
        assert result["min_instances"] == 2
        assert result["max_instances"] == 10
        assert len(result["metric_providers"]) == 1
        assert result["metric_providers"][0]["type"] == "cpu"


class TestPaastaShowMetricProviders:
    @patch("paasta_tools.cli.cmds.show_metric_providers.figure_out_service_name")
    @patch(
        "paasta_tools.cli.cmds.show_metric_providers.get_instance_configs_for_service"
    )
    def test_no_instances_found(self, mock_get_configs, mock_figure_service):
        """Test behavior when no instances are found"""
        mock_figure_service.return_value = "test-service"
        mock_get_configs.return_value = []

        mock_args = Mock(autospec=None)
        mock_args.soa_dir = "/test/soa"
        mock_args.instances = None
        mock_args.clusters = None
        mock_args.json = False

        with patch("builtins.print") as mock_print:
            result = paasta_show_metric_providers(mock_args)

        assert result == 1
        assert mock_print.call_count > 0

    @patch("paasta_tools.cli.cmds.show_metric_providers.figure_out_service_name")
    @patch(
        "paasta_tools.cli.cmds.show_metric_providers.get_instance_configs_for_service"
    )
    def test_no_autoscaling_capable_instances(
        self, mock_get_configs, mock_figure_service
    ):
        """Test behavior when no autoscaling-capable instances are found"""
        mock_figure_service.return_value = "test-service"

        # Mock a non-autoscaling instance type (not Kubernetes or EKS)
        mock_instance = Mock(autospec=None)
        mock_get_configs.return_value = [mock_instance]

        mock_args = Mock(autospec=None)
        mock_args.soa_dir = "/test/soa"
        mock_args.instances = None
        mock_args.clusters = None
        mock_args.json = False

        with patch("builtins.print") as mock_print:
            result = paasta_show_metric_providers(mock_args)

        assert result == 1
        assert mock_print.call_count > 0

    @patch("paasta_tools.cli.cmds.show_metric_providers.figure_out_service_name")
    @patch(
        "paasta_tools.cli.cmds.show_metric_providers.get_instance_configs_for_service"
    )
    def test_successful_execution_human_readable(
        self, mock_get_configs, mock_figure_service
    ):
        """Test successful execution with human-readable output"""
        mock_figure_service.return_value = "test-service"

        # Mock a Kubernetes instance with autoscaling
        mock_k8s_instance = Mock(autospec=None, spec=KubernetesDeploymentConfig)
        mock_k8s_instance.cluster = "test-cluster"
        mock_k8s_instance.instance = "main"
        mock_k8s_instance.is_autoscaling_enabled.return_value = True
        mock_k8s_instance.get_min_instances.return_value = 2
        mock_k8s_instance.get_max_instances.return_value = 10
        mock_k8s_instance.get_autoscaling_params.return_value = {
            "metrics_providers": [
                {"type": "cpu", "setpoint": 0.7, "decision_policy": "proportional"}
            ]
        }

        mock_get_configs.return_value = [mock_k8s_instance]

        mock_args = Mock(autospec=None)
        mock_args.soa_dir = "/test/soa"
        mock_args.instances = None
        mock_args.clusters = None
        mock_args.json = False

        with patch("builtins.print") as mock_print:
            result = paasta_show_metric_providers(mock_args)

        assert result == 0
        assert mock_print.call_count > 0

    @patch("paasta_tools.cli.cmds.show_metric_providers.figure_out_service_name")
    @patch(
        "paasta_tools.cli.cmds.show_metric_providers.get_instance_configs_for_service"
    )
    def test_successful_execution_json_output(
        self, mock_get_configs, mock_figure_service
    ):
        """Test successful execution with JSON output"""
        mock_figure_service.return_value = "test-service"

        # Mock a Kubernetes instance with autoscaling
        mock_k8s_instance = Mock(autospec=None, spec=KubernetesDeploymentConfig)
        mock_k8s_instance.cluster = "test-cluster"
        mock_k8s_instance.instance = "main"
        mock_k8s_instance.is_autoscaling_enabled.return_value = True
        mock_k8s_instance.get_min_instances.return_value = 2
        mock_k8s_instance.get_max_instances.return_value = 10
        mock_k8s_instance.get_autoscaling_params.return_value = {
            "metrics_providers": [
                {"type": "cpu", "setpoint": 0.7, "decision_policy": "proportional"}
            ],
            "setpoint": 0.7,
        }

        mock_get_configs.return_value = [mock_k8s_instance]

        mock_args = Mock(autospec=None)
        mock_args.soa_dir = "/test/soa"
        mock_args.instances = None
        mock_args.clusters = None
        mock_args.json = True

        with patch("builtins.print") as mock_print:
            result = paasta_show_metric_providers(mock_args)

        assert result == 0
        mock_print.assert_called()

        # Verify JSON output was printed
        printed_output = mock_print.call_args[0][0]
        parsed_json = json.loads(printed_output)
        assert len(parsed_json) == 1
        assert parsed_json[0]["service"] == "test-service"
        assert parsed_json[0]["cluster"] == "test-cluster"
        assert parsed_json[0]["instance"] == "main"
        assert parsed_json[0]["autoscaling_enabled"] is True

    @patch("paasta_tools.cli.cmds.show_metric_providers.figure_out_service_name")
    @patch(
        "paasta_tools.cli.cmds.show_metric_providers.get_instance_configs_for_service"
    )
    def test_filters_instances_and_clusters(
        self, mock_get_configs, mock_figure_service
    ):
        """Test that instance and cluster filtering works"""
        mock_figure_service.return_value = "test-service"
        mock_get_configs.return_value = []

        mock_args = Mock(autospec=None)
        mock_args.soa_dir = "/test/soa"
        mock_args.instances = "main,canary"
        mock_args.clusters = "prod,staging"
        mock_args.json = False

        paasta_show_metric_providers(mock_args)

        # Verify get_instance_configs_for_service was called with filtered values
        mock_get_configs.assert_called_once_with(
            service="test-service",
            soa_dir="/test/soa",
            clusters=["prod", "staging"],
            instances=["main", "canary"],
        )

    @patch("paasta_tools.cli.cmds.show_metric_providers.figure_out_service_name")
    @patch(
        "paasta_tools.cli.cmds.show_metric_providers.get_instance_configs_for_service"
    )
    def test_no_autoscaling_instances_found(
        self, mock_get_configs, mock_figure_service
    ):
        """Test behavior when instances exist but none have autoscaling enabled"""
        mock_figure_service.return_value = "test-service"

        # Mock Kubernetes instance without autoscaling
        mock_k8s_instance = Mock(autospec=None, spec=KubernetesDeploymentConfig)
        mock_k8s_instance.cluster = "test-cluster"
        mock_k8s_instance.instance = "main"
        mock_k8s_instance.is_autoscaling_enabled.return_value = False
        mock_get_configs.return_value = [mock_k8s_instance]

        mock_args = Mock(autospec=None)
        mock_args.soa_dir = "/test/soa"
        mock_args.instances = None
        mock_args.clusters = None
        mock_args.json = False

        with patch("builtins.print") as mock_print:
            result = paasta_show_metric_providers(mock_args)

        assert (
            result == 0
        )  # Should return 0 in this case according to the implementation
        assert mock_print.call_count > 0
