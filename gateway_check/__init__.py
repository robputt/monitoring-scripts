import os
import sys
import json
import logging
import datetime
import requests
from dateutil.parser import parse as dt_parse


logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s',
                    level=logging.INFO,
                    stream=sys.stdout)


NOC_URL = 'http://noc.thethingsnetwork.org:8085/api/v2/gateways'


def get_config():
    try:
        config_file = os.environ['CONFIG_FILE']
        with open(config_file, 'r') as fhandle:
            config_data = json.load(fhandle)

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


def run_gateway_check():
    logging.info("Loading configuration file")
    get_config()
    logging.info("Fetching gateways from inventory")
    gateways = get_gateways_from_inventory()

    logging.info("Checking network connection data for gateways...")
    for gateway in gateways:
        logging.info("Checking %s" % gateway.get('name'))
        gw_data = get_noc_data(gateway.get('ttn_id'))
        logging.info("Got NOC data for gateway: %s" % gw_data)
        utc_recent = datetime.datetime.utcnow().replace(tzinfo=None) - datetime.timedelta(minutes=10)
        utc_gw = dt_parse(gw_data.get('timestamp')).replace(tzinfo=None)

        if utc_gw < utc_recent:
            logging.info("Gateway has not been seen recently, marking as offline.")
        else:
            logging.info("Gateway has been seen recently, marking as online.")


if __name__ == '__main__':
    run_gateway_check()
