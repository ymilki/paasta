#!/usr/bin/env python
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
from typing import Dict
from typing import Optional

from paasta_tools.cli.utils import figure_out_service_name
from paasta_tools.cli.utils import get_instance_configs_for_service
from paasta_tools.cli.utils import lazy_choices_completer
from paasta_tools.cli.utils import list_instances
from paasta_tools.eks_tools import EksDeploymentConfig
from paasta_tools.kubernetes_tools import KubernetesDeploymentConfig
from paasta_tools.long_running_service_tools import LongRunningServiceConfig
from paasta_tools.utils import DEFAULT_SOA_DIR
from paasta_tools.utils import list_clusters
from paasta_tools.utils import list_services
from paasta_tools.utils import PaastaColors


def add_subparser(subparsers):
    show_metric_providers_parser = subparsers.add_parser(
        "show-metric-providers",
        help="Show autoscaling metric providers configured for service instances.",
        description=(
            "'paasta show-metric-providers' displays the autoscaling metric providers "
            "and their configuration parameters for each instance of a service. "
            "This helps understand what metrics drive autoscaling decisions."
        ),
    )
    show_metric_providers_parser.add_argument(
        "-s",
        "--service",
        help="The name of the service you wish to inspect",
    ).completer = lazy_choices_completer(list_services)
    show_metric_providers_parser.add_argument(
        "-i",
        "--instances",
        help="A comma-separated list of instances to inspect. If not specified, shows all instances.",
        default=None,
    ).completer = lazy_choices_completer(list_instances)
    show_metric_providers_parser.add_argument(
        "-c",
        "--clusters",
        help="A comma-separated list of clusters to inspect. If not specified, shows all clusters.",
        default=None,
    ).completer = lazy_choices_completer(list_clusters)
    show_metric_providers_parser.add_argument(
        "-d",
        "--soa-dir",
        dest="soa_dir",
        metavar="SOA_DIR",
        default=DEFAULT_SOA_DIR,
        help="define a different soa config directory",
    )
    show_metric_providers_parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format",
    )
    show_metric_providers_parser.set_defaults(command=paasta_show_metric_providers)


def format_metric_provider(provider: Dict) -> str:
    """Format a single metric provider configuration for display."""
    lines = []
    provider_type = provider.get("type", "unknown")
    lines.append(f"    Type: {PaastaColors.cyan(provider_type)}")

    # Show key parameters
    if "setpoint" in provider:
        setpoint = provider["setpoint"]
        if provider_type == "cpu":
            lines.append(
                f"      Setpoint: {PaastaColors.green(f'{setpoint * 100:.1f}%')} CPU utilization"
            )
        else:
            lines.append(f"      Setpoint: {PaastaColors.green(str(setpoint))}")

    if "decision_policy" in provider:
        lines.append(
            f"      Decision Policy: {PaastaColors.yellow(provider['decision_policy'])}"
        )

    # Show additional parameters
    additional_params = {
        k: v
        for k, v in provider.items()
        if k not in ["type", "setpoint", "decision_policy"]
    }
    if additional_params:
        lines.append(f"      Additional Parameters:")
        for key, value in additional_params.items():
            lines.append(f"        {key}: {PaastaColors.grey(str(value))}")

    return "\n".join(lines)


def format_instance_info(
    service: str,
    cluster: str,
    instance: str,
    config: LongRunningServiceConfig,
    json_output: bool = False,
) -> Optional[Dict]:
    """Format information for a single instance."""
    if not config.is_autoscaling_enabled():
        if not json_output:
            return None
        else:
            return {
                "service": service,
                "cluster": cluster,
                "instance": instance,
                "autoscaling_enabled": False,
                "metric_providers": [],
            }

    autoscaling_params = config.get_autoscaling_params()
    metric_providers = autoscaling_params.get("metrics_providers", [])

    if json_output:
        return {
            "service": service,
            "cluster": cluster,
            "instance": instance,
            "autoscaling_enabled": True,
            "min_instances": config.get_min_instances(),
            "max_instances": config.get_max_instances(),
            "metric_providers": metric_providers,
            "autoscaling_params": autoscaling_params,
        }
    else:
        # Format for human-readable output
        lines = []
        lines.append(f"  {PaastaColors.bold(f'{cluster}.{instance}')}")
        lines.append(
            f"    Min/Max Instances: {config.get_min_instances()}/{config.get_max_instances()}"
        )
        lines.append(f"    Metric Providers ({len(metric_providers)}):")

        if not metric_providers:
            lines.append(
                f"      {PaastaColors.red('None configured (using defaults)')}"
            )
        else:
            for i, provider in enumerate(metric_providers, 1):
                lines.append(f"      {PaastaColors.bold(f'Provider {i}:')}")
                lines.append(format_metric_provider(provider))

        return {"formatted_output": "\n".join(lines)}


def paasta_show_metric_providers(args):
    """Main command function to show metric providers."""
    service = figure_out_service_name(args, soa_dir=args.soa_dir)

    # Parse instances and clusters from command line
    target_instances = []
    if args.instances:
        target_instances = [i.strip() for i in args.instances.split(",")]

    target_clusters = []
    if args.clusters:
        target_clusters = [c.strip() for c in args.clusters.split(",")]

    # Get all instance configurations
    instance_configs = list(
        get_instance_configs_for_service(
            service=service,
            soa_dir=args.soa_dir,
            clusters=target_clusters if target_clusters else None,
            instances=target_instances if target_instances else None,
        )
    )

    if not instance_configs:
        print(
            f"{PaastaColors.red('No instances found')} for service {PaastaColors.bold(service)}"
        )
        if target_instances:
            print(f"Requested instances: {', '.join(target_instances)}")
        if target_clusters:
            print(f"Requested clusters: {', '.join(target_clusters)}")
        return 1

    # Filter for autoscaling-capable instance types
    autoscaling_configs = []
    for config in instance_configs:
        if isinstance(config, (KubernetesDeploymentConfig, EksDeploymentConfig)):
            autoscaling_configs.append(config)

    if not autoscaling_configs:
        print(
            f"{PaastaColors.yellow('No autoscaling-capable instances found')} for service {PaastaColors.bold(service)}"
        )
        print("Only Kubernetes and EKS instances support autoscaling.")
        return 1

    # Collect and format output
    results = []
    for config in autoscaling_configs:
        result = format_instance_info(
            service=service,
            cluster=config.cluster,
            instance=config.instance,
            config=config,
            json_output=args.json,
        )
        if result:
            results.append(result)

    # Output results
    if args.json:
        print(json.dumps(results, indent=2, sort_keys=True))
    else:
        if not results:
            print(
                f"{PaastaColors.yellow('No instances with autoscaling enabled')} found for service {PaastaColors.bold(service)}"
            )
            return 0

        print(f"Metric providers for service {PaastaColors.bold(service)}:")
        print()

        for result in results:
            if "formatted_output" in result:
                print(result["formatted_output"])
                print()

    return 0
