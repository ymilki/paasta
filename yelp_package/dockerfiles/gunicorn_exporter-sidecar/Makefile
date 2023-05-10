EXPORTER_REPO ?= https://github.com/prometheus/statsd_exporter
EXPORTER_TAG ?= v0.24.0
YELP_SUFFIX ?= yelp1

DOCKER_IMAGE ?= docker-dev.yelpcorp.com/gunicorn_exporter-k8s-sidecar:$(EXPORTER_TAG)-$(YELP_SUFFIX)

all: docker_image push

statsd_exporter:
	git clone --branch $(EXPORTER_TAG) $(EXPORTER_REPO)

checkout: statsd_exporter
	git -C statsd_exporter fetch --tags $(EXPORTER_REPO)
	git -C statsd_exporter checkout --force $(EXPORTER_TAG)

statsd_exporter/statsd_exporter: checkout
	make -C statsd_exporter

docker_image: statsd_exporter/statsd_exporter
	docker build -t $(DOCKER_IMAGE) .

push: docker_image
	docker push $(DOCKER_IMAGE)
