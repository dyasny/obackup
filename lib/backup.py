#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import logging
import os
import time
import uuid
import backy2

import ovirtsdk4 as sdk
import ovirtsdk4.types as types

def backup(connection, AGENT_VM_NAME="obackup", DATA_VM_NAME,
                        APPLICATION_NAME="obackup", DATA_DISKS, CONF):
    # Get the reference to the root of the services tree:
    system_service = connection.system_service()

    # Get the reference to the service that we will use to send events to
    # the audit log:
    events_service = system_service.events_service()

    # In order to send events we need to also send unique integer ids. These
    # should usually come from an external database, but in this example we
    # will just generate them from the current time in seconds since Jan 1st
    # 1970.
    event_id = int(time.time())

    # Get the reference to the service that manages the virtual machines:
    vms_service = system_service.vms_service()

    # Find the virtual machine that we want to back up. Note that we need to
    # use the 'all_content' parameter to retrieve the retrieve the OVF, as
    # it isn't retrieved by default:
    data_vm = vms_service.list(
        search='name=%s' % DATA_VM_NAME,
        all_content=True,
    )[0]
    logging.info(
        'Found data virtual machine \'%s\', the id is \'%s\'.',
        data_vm.name, data_vm.id,
    )

    # Find the virtual machine were we will attach the disks in order to do
    # the backup:
    agent_vm = vms_service.list(
        search='name=%s' % AGENT_VM_NAME,
    )[0]
    logging.info(
        'Found agent virtual machine \'%s\', the id is \'%s\'.',
        agent_vm.name, agent_vm.id,
    )

    # Find the services that manage the data and agent virtual machines:
    data_vm_service = vms_service.vm_service(data_vm.id)
    agent_vm_service = vms_service.vm_service(agent_vm.id)

    # Create an unique description for the snapshot, so that it is easier
    # for the administrator to identify this snapshot as a temporary one
    # created just for backup purposes:
    snap_description = '%s_obackup_%s' % (data_vm.name, uuid.uuid4())

    # Send an external event to indicate to the administrator that the
    # backup of the virtual machine is starting. Note that the description
    # of the event contains the name of the virtual machine and the name of
    # the temporary snapshot, this way, if something fails, the administrator
    # will know what snapshot was used and remove it manually.
    events_service.add(
        event=types.Event(
            vm=types.Vm(
              id=data_vm.id,
            ),
            origin=APPLICATION_NAME,
            severity=types.LogSeverity.NORMAL,
            custom_id=event_id,
            description=(
                'Backup of virtual machine \'%s\' using snapshot \'%s\' is '
                'starting.' % (data_vm.name, snap_description)
            ),
        ),
    )
    event_id += 1

    # Save the OVF to a file, so that we can use to restore the virtual
    # machine later. The name of the file is the name of the virtual
    # machine, followed by a dash and the identifier of the virtual machine,
    # to make it unique:

    ovf_data = data_vm.initialization.configuration.data
    ovf_file = '%s-%s.ovf' % (data_vm.name, data_vm.id)
    with open(ovf_file, 'w') as ovs_fd:
        ovs_fd.write(ovf_data.encode('utf-8'))
    logging.info('Wrote OVF to file \'%s\'.', os.path.abspath(ovf_file))

    vms_config_path = CONF['appliance_configuration']['vms_path']
    vm_config_file = vms_config_path + data_vm.name + ".yml"
    data_vm_nics_service = data_vm_service.nics_service()
    data_vm_nics = data_vm_nics_service.list()
    nics = []
    for nic in data_vm_nics:
        n = {"interface" : nic.interface.value, "mac": nic.mac.address}
        nics.append(n)
    data_vm_disks = []
    data_vm_disk_attachment_service = data_vm_service.disk_attachments_service()
    data_vm_disk_attachments = data_vm_disk_attachment_service.list()
    for disk in data_vm_disk_attachments:
        if disk.id in DATA_DISKS:
            d = {
                "id" : disk.id,
                "bootable": disk.bootable,
                "interface": disk.interface.value,
                "pass_discard": disk.pass_discard
                }
            data_vm_disks.append(d)
    vm_dict = {
        "name" : data_vm.name,
        "cluster" : data_vm.cluster.id,
        "cpu" : {
            "architecture" : data_vm.cpu.architecture.name,
            "sockets" : data_vm.cpu.topology.sockets,
            "cores" : data_vm.cpu.topology.cores,
            "threads" : data_vm.cpu.topology.threads
            },
        "memory" : data_vm.memory,
        "memory_policy" : {
            "max" : data_vm.memory_policy.max,
            "ballooning" : data_vm.memory_policy.ballooning,
            "guaranteed" : data_vm.memory_policy.guaranteed,
            },
        "description" : data_vm.description,
        "nics" : nics,
        "disk_attachments" : data_vm_disks,
        "display" : data_vm.display.type.name,
        "time_zone" : data_vm.time_zone.name,
        "os" : data_vm.os.type,
        "type" : data_vm.type.name,
        "virtio_scsi" : data_vm.virtio_scsi.enabled,
        "high_availability" : data_vm.high_availability.enabled,
    }
    with open(vm_config_file, 'w') as f:
        f.write(yaml.dump(vm_dict))
    bkp_status = backy2.backup_vm_settings(data_vm.name, vm_config_file)
    if bkp_status != "Compete":
        logging.error("Failed to save VM configuration for %s" % data_vm.name)

    # Send the request to create the snapshot. Note that this will return
    # before the snapshot is completely created, so we will later need to
    # wait till the snapshot is completely created.
    # The snapshot will not include memory. Change to True the parameter
    # persist_memorystate to get it (in that case the VM will be paused for a while).
    snaps_service = data_vm_service.snapshots_service()
    snap = snaps_service.add(
        snapshot=types.Snapshot(
            description=snap_description,
            persist_memorystate=False,
        ),
    )
    logging.info(
        'Sent request to create snapshot \'%s\', the id is \'%s\'.',
        snap.description, snap.id,
    )

    # Poll and wait till the status of the snapshot is 'ok', which means
    # that it is completely created:
    snap_service = snaps_service.snapshot_service(snap.id)
    while snap.snapshot_status != types.SnapshotStatus.OK:
        logging.info(
            'Waiting till the snapshot is created, the satus is now \'%s\'.',
            snap.snapshot_status,
        )
        time.sleep(1)
        snap = snap_service.get()
    logging.info('The snapshot is now complete.')

    # Retrieve the descriptions of the disks of the snapshot:
    snap_disks_service = snap_service.disks_service()
    snap_disks = snap_disks_service.list()

    # Attach all the disks of the snapshot to the agent virtual machine, and
    # save the resulting disk attachments in a list so that we can later
    # detach them easily:
    attachments_service = agent_vm_service.disk_attachments_service()
    attachments = []
    attachment_map = {}
    alphabet = map(chr, range(97, 123))
    blkid = 0
    for snap_disk in snap_disks:
        if snap_disk.id in DATA_DISKS:
            blkid += 1
            attachment = attachments_service.add(
                attachment=types.DiskAttachment(
                    disk=types.Disk(
                        id=snap_disk.id,
                        snapshot=types.Snapshot(
                            id=snap.id,
                        ),
                    ),
                    active=True,
                    bootable=False,
                    interface=types.DiskInterface.VIRTIO,
                ),
            )
            attachments.append(attachment)
            attachment_map["vd" + alphabet[blkid]] = attachment

    # Insert here the code to contact the backup agent and do the actual
    # backup ...
    logging.info('Doing the actual backup ...')
    for vdisk in attachment_map.keys():
        logging.info(
            'Backing up disk \'%s\'.',
            attachment_map[vdisk].id
        )
        backup_status = backy2.backup_disk(vdisk, attachment_map[vdisk].id,
                                                snap_description, data_vm.name)
        if backup_status == "Failed":
            logging.error(
                'Failed to back up VM %s Disk %s, check backy2 logs',
                data_vm.name, attachment_map[vdisk].id
            )
            events_service.add(
                event=types.Fault(
                    vm=types.Vm(
                      id=data_vm.id,
                    ),
                    origin=APPLICATION_NAME,
                    severity=types.LogSeverity.ERROR,
                    custom_id=event_id,
                    description=(
                        'Backup of /VM \'%s\' disk %s failed',
                        data_vm.name, attachment_map[vdisk].id
                    ),
                ),
            )
            event_id += 1

    # Detach the disks from the agent virtual machine:
    for attachment in attachments:
        attachment_service = attachments_service.attachment_service(attachment.id)
        attachment_service.remove()

    # Remove the snapshot:
    snap_service.remove()
    logging.info('Removed the snapshot \'%s\'.', snap.description)

    # Send an external event to indicate to the administrator that the
    # backup of the virtual machine is completed:
    events_service.add(
        event=types.Event(
            vm=types.Vm(
              id=data_vm.id,
            ),
            origin=APPLICATION_NAME,
            severity=types.LogSeverity.NORMAL,
            custom_id=event_id,
            description=(
                'Backup of virtual machine \'%s\' using snapshot \'%s\' is '
                'completed.' % (data_vm.name, snap_description)
            ),
        ),
    )
    event_id += 1
