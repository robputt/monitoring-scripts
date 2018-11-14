import os
import sys
import json
import logging
import datetime
import requests
from dateutil.parser import parse as dt_parse
from influxdb import InfluxDBClient


logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s',
                    level=logging.INFO,
                    stream=sys.stdout)


NOC_URL = 'http://noc.thethingsnetwork.org:8085/api/v2/gateways'


def get_config():
    try:
        config_file = os.environ['CONFIG_FILE']
        with open(config_file, 'r') as fhandle:
            config_data = json.load(fhandle)
            return config_data

    except json.decoder.JSONDecodeError:
        logging.error("Configuration file does not appear to be "
                      "valid JSON")
        sys.exit(1)

    except FileNotFoundError:
        logging.error("Configuration file was not found at %s"
                      % config_file)
        sys.exit(1)

    except KeyError:
        logging.error("Configuration file is missing required key.")
        sys.exit(1)


def get_gateways_from_inventory():
    gateways = []
    try:
        inventory_dir = os.environ['INVENTORY']
        inventory_files = os.listdir(inventory_dir)

        if inventory_files:
            for file in inventory_files:
                if 'gw' in file:
                    try:
                        logging.info("Loading %s from inventory" % file)
                        inventory_file = '%s/%s' % (inventory_dir, file)
                        with open(inventory_file, 'r') as fhandle:
                            gw_data = json.load(fhandle)
                            gateways.append(gw_data)

                    except json.decoder.JSONDecodeError:
                        logging.error("Inventory file does not appear to "
                                      "be valid JSON - skipping")

                    except KeyError:
                        logging.error("Inventory file is missing required "
                                      "key - skipping")

                    logging.info("Loaded gateway inventory data: %s" % gw_data)

        else:
            logging.error("Unable to load inventory, no files found.")

    except Exception as err:
        logging.error("Error occured whilst loading inventory: %s" % err)

    return gateways


def get_noc_data(gateway_id):
    try:
        noc_resp = requests.get('%s/%s' % (NOC_URL, gateway_id))
        if noc_resp.status_code == 404:
            old_url = 'eui-%s' % gateway_id
            noc_resp = requests.get('%s/%s' % (NOC_URL, old_url.lower()))

        json_resp = json.loads(noc_resp.text)
        if json_resp.get('timestamp'):
            return json_resp
        else:
            raise Exception("Gateway not found via NOC API")

    except Exception as err:
        logging.error("Error fetching gateway data from TTN NOC API: "
                      "%s" % str(err))


def insert_gw_status(config, gateway_id, status):
    try:
        influx_client = InfluxDBClient(config.get('influxdb_host'),
                                       config.get('influxdb_port'),
                                       config.get('influxdb_user'),
                                       config.get('influxdb_pass'),
                                       config.get('influxdb_name'))

        db_json = [{"measurement": "gateways",
                    "tags": {"device_id": gateway_id},
                    "time": datetime.datetime.now(),
                    "fields": {"status": status}
                    }]

        logging.info("Sending data to InfluxDB: %s" % db_json)
        influx_client.write_points(db_json)

    except Exception as err:
        logging.error("Error inserting data into InfluxDB: %s" % str(err))


def insert_gw_packet_count(config, gateway_id, rx_count, tx_count):
    try:
        influx_client = InfluxDBClient(config.get('influxdb_host'),
                                       config.get('influxdb_port'),
                                       config.get('influxdb_user'),
                                       config.get('influxdb_pass'),
                                       config.get('influxdb_name'))

        db_json = [{"measurement": "gateway_packet_count",
                    "tags": {"device_id": gateway_id},
                    "time": datetime.datetime.now(),
                    "fields": {"rx": rx_count,
                               "tx": tx_count}
                    }]

        logging.info("Sending data to InfluxDB: %s" % db_json)
        influx_client.write_points(db_json)

    except Exception as err:
        logging.error("Error inserting data into InfluxDB: %s" % str(err))


def run_gateway_check():
    logging.info("Loading configuration file")
    config = get_config()
    logging.info("Fetching gateways from inventory")
    gateways = get_gateways_from_inventory()

    logging.info("Checking network connection data for gateways...")
    for gateway in gateways:
        try:
            logging.info("Checking %s" % gateway.get('name'))
            gw_data = get_noc_data(gateway.get('ttn_id'))
            logging.info("Got NOC data for gateway: %s" % gw_data)
            utc_now = datetime.datetime.utcnow().replace(tzinfo=None)
            utc_recent = utc_now - datetime.timedelta(minutes=10)
            utc_gw = dt_parse(gw_data.get('timestamp')).replace(tzinfo=None)

            if utc_gw < utc_recent:
                logging.info("Gateway has not been seen recently, marking as "
                             " offline.")
                insert_gw_status(config, gateway.get('ttn_id'), 0)
            else:
                logging.info("Gateway has been seen recently, marking as "
                             "online.")
                insert_gw_status(config, gateway.get('ttn_id'), 1)

            insert_gw_packet_count(config,
                                   gateway.get('ttn_id'),
                                   gw_data.get('rx_ok'),
                                   0)

        except Exception as err:
            logging.error("Error occured dealing with gateway: %s" % str(err))


if __name__ == '__main__':
    run_gateway_check()
