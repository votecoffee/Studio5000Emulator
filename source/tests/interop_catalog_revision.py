"""Independent cache-comparison and refresh checks across isolated imports."""
import argparse
import base64
import json
import struct
import tempfile
from pathlib import Path
from xml.etree import ElementTree as E
from interop_atomic_transfers import documented_catalog
from logixlab.server import Application, BASE
from logixlab.ethernetip import Endpoint


def read_revision(driver):
    result = driver.generic_message(service=3, class_code=0xAC, instance=1, connected=True,
        request_data=struct.pack('<6H', 5, 1, 2, 3, 4, 10), return_response_packet=True)
    packet = result.value; assert packet.service_status == 0, result.error
    data = packet.data; assert struct.unpack_from('<H', data)[0] == 5
    pos = 2; values = []
    for attribute, width in ((1, 2), (2, 2), (3, 4), (4, 4), (10, 4)):
        assert struct.unpack_from('<HH', data, pos) == (attribute, 0); pos += 4
        values.append(data[pos:pos + width]); pos += width
    assert pos == len(data)
    return b''.join(values).hex()


def check(app, endpoint):
    from pycomm3 import LogixDriver, __version__
    target = f'127.0.0.1:{endpoint.port}'
    def client():
        driver = LogixDriver(target + '/0', init_tags=False)
        driver._cfg['extended forward open'] = False; driver._cfg['connection_size'] = 256
        return driver
    with client() as driver:
        class_metadata = driver.generic_message(service=3, class_code=0xAC, instance=0, connected=True,
            request_data=struct.pack('<4H', 3, 1, 2, 3), return_response_packet=True).value
        assert class_metadata.service_status == 0
        assert class_metadata.data == struct.pack('<10H', 3, 1, 0, 1, 2, 0, 1, 3, 0, 1)
        before = read_revision(driver)
        driver._tags = documented_catalog(driver, structures=True)
        old_instance = driver.tags['Records']['instance_id']
        assert driver.data_types['MixedRecord']['template']['structure_size'] == 64
        app.command('write', {'tag': 'Records[0].Count', 'value': 777}); app.command('step', {})
        observed = driver.read('Observed'); assert observed and observed.value == 777, observed
        assert read_revision(driver) == before
    app.command('reset', {})
    with client() as driver: assert read_revision(driver) == before
    tree = E.parse(BASE / 'samples/LayoutLab.L5X'); root = tree.getroot()
    tag = E.SubElement(tree.find('./Controller/Tags'), 'Tag', Name='Added', TagType='Base', DataType='DINT', ExternalAccess='Read/Write')
    E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'DataValue', DataType='DINT', Value='42')
    def load():
        data = E.tostring(root, encoding='utf-8')
        app.command('load', {'name': 'catalog-refresh.L5X', 'content': base64.b64encode(data).decode('ascii')})
    load()
    with client() as driver:
        after_tag = read_revision(driver); assert after_tag != before
        driver._tags = documented_catalog(driver, structures=True)
        assert driver.tags['Records']['instance_id'] != old_instance, 'Fixture did not change symbol instances'
        added = driver.read('Added'); assert added and added.value == 42, added
    members = tree.find('./Controller/DataTypes/DataType[@Name="SmallGroup"]/Members')
    E.SubElement(members, 'Member', Name='Extra', DataType='DINT', Dimension='0', Hidden='false', ExternalAccess='Read/Write')
    for node in root.findall('.//StructureMember[@DataType="SmallGroup"]'):
        E.SubElement(node, 'DataValueMember', Name='Extra', DataType='DINT', Value='0')
    load()
    with client() as driver:
        after_type = read_revision(driver); assert after_type != after_tag
        driver._tags = documented_catalog(driver, structures=True)
        assert driver.data_types['MixedRecord']['template']['structure_size'] == 72
        extra = driver.read('Records[0].Group.Extra'); assert extra and extra.value == 0, extra
        records = driver.read('Records{8}'); assert records and len(records.value) == 8, records
        assert all(record['Group']['Extra'] == 0 for record in records.value)
        assert read_revision(driver) == after_type
    events = endpoint.state(True)['events']
    assert any(e.get('service') == '0x03' and 'class_id=172,' in e.get('path', '') and e.get('status') == 0 for e in events)
    assert any(e.get('service') == '0x4E' and 'class_id=6,' in e.get('path', '') and e.get('status') == 0 for e in events)
    return {'client': 'pycomm3.LogixDriver', 'client_version': __version__, 'target': target,
            'catalog_adapter': 'Documented symbol/template reads; native tag upload not used',
            'controller_attributes': [1, 2, 3, 4, 10], 'attribute_widths': [2, 2, 4, 4, 4],
            'controller_class_revision': 1, 'controller_max_instance': 1, 'controller_instance_count': 1,
            'runtime_changes_preserved_token': True, 'reset_preserved_token': True,
            'tag_change_detected': True, 'symbol_instances_refreshed': True,
            'udt_change_detected': True, 'record_size_before': 64, 'record_size_after': 72,
            'new_member_read': True, 'refreshed_records_read': 8,
            'token_before': before, 'token_after_tag': after_tag, 'token_after_type': after_type,
            'forward_close': True, 'native_firmware_signature': False, 'studio_go_online': 'UNVERIFIED'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--out', required=True); args = parser.parse_args()
    with tempfile.TemporaryDirectory() as folder:
        app = Application(folder); app.command('demo', {'sample': 'LayoutLab'})
        endpoint = Endpoint(app, 0, False, 'logix-v35-l85e').start(); app.endpoint = endpoint
        try: result = check(app, endpoint)
        except Exception:
            Path(args.out).with_suffix('.failure-trace.json').write_text(json.dumps(endpoint.state(True), indent=2), encoding='utf-8')
            raise
        finally: app.close()
    Path(args.out).write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
