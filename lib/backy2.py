import subprocess
import sys
import os
import logging

def backup_disk(vdx, disk_id, snap_description, vm_name):
    #backy2 backup -t this_is_a_tag file:///dev/vdX backup_name
    backup_src = ('file:///dev/%s' % vdx)
    backup_name = ("%s_DISK_%s" % (vm_name, disk_id))
    cmd = ['sudo', 'backy2', 'backup', '-t', snap_description,
            backup_src, backup_name]
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        out = p.communicate()[0]
        rc = p.returncode
    except Exception, e:
        print("Unknown exception %s, output: %s" % str(e))
    if rc != 0:
        print("Failed to run backy2 backup, please check the backy2 logs")
        return "Failed"
    else:
        print(
            'Backup of disk %s belonging to VM %s complete', 
            disk_id, vm_name
            )
        return "Complete"

def backup_vm_settings(vm_name, vm_data_file):
    backup_src = ('file:///dev/%s' % vm_data_file)
    backup_name = ("%s_CONF" % vm_name)
    cmd = ['sudo', 'backy2', 'backup', backup_src, backup_name]
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        out = p.communicate()[0]
        rc = p.returncode
    except Exception, e:
        print("Unknown exception %s, output: %s" % str(e))
    if rc != 0:
        print("Failed to run backy2 backup, please check the backy2 logs")
        return "Failed"
    else:
        print("Backup of VM %s settings complete" % vm_name)
        return "Complete"


def print_backups():
    pass
