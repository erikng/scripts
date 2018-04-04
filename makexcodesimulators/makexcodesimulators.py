#!/usr/bin/python
# encoding: utf-8

# Written by Erik Gomez
# Lots of code and functions taken from installinstallmacos.py

#
# Thanks to Greg Neagle for most of the working/good code.
#

'''makexcodesimulators.py
A tool to download and create distribution packages to properly install
xcode simulators via your tool of choice.

This has only been tested on Xcode 9.3 so YMMV'''


import argparse
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import urlparse
from xml.parsers.expat import ExpatError
sys.path.append('/usr/local/munki')
from munkilib import FoundationPlist  # noqa


class ReplicationError(Exception):
    '''A custom error when replication fails'''
    pass


DISTRIBUTIONPLIST = """<?xml version="1.0" encoding="utf-8"?>
<installer-gui-script minSpecVersion="1">"""


def get_xcode_info(xcodepath):
    keys_to_get = ['DVTPlugInCompatibilityUUID', 'DTXcode']
    keys_obtained = {}
    xcode_info_plist_path = os.path.join(xcodepath, 'Contents/Info.plist')
    xcode_info_plist = FoundationPlist.readPlist(xcode_info_plist_path)
    for xcode_key in keys_to_get:
        if xcode_key in xcode_info_plist:
            if xcode_key == 'DTXcode':
                xcode_key_value = xcode_info_plist[xcode_key]
                # You get something back like 0930
                if xcode_key_value.startswith('0'):
                    # We strip the first character to end up with 930
                    xcode_key_value = xcode_key_value[1:]
                # Now we take 930, convert to a list and then join it. This
                # will give us 9.3.0
                xcode_key_value = '.'.join(list(xcode_key_value))
                # Return the value
                keys_obtained[xcode_key] = xcode_key_value
            else:
                keys_obtained[xcode_key] = xcode_info_plist[xcode_key]
    return keys_obtained


def replicate_url(full_url, temp_dir, show_progress=False):
    relative_url = full_url.split('/')[-1]
    local_file_path = os.path.join(temp_dir, relative_url)
    if show_progress:
        options = '-fL'
    else:
        options = '-sfL'
    curl_cmd = ['/usr/bin/curl', options, '--create-dirs',
                '-o', local_file_path]
    if os.path.exists(local_file_path):
        curl_cmd.extend(['-z', local_file_path])
    curl_cmd.append(full_url)
    print "Downloading %s to %s..." % (full_url, relative_url)
    try:
        subprocess.check_call(curl_cmd)
    except subprocess.CalledProcessError, err:
        raise ReplicationError(err)
    return local_file_path


def download_and_parse_xcode_catalog(temp_dir, xcode_version, xcode_uuid):
    url = 'https://devimages-cdn.apple.com/downloads/xcode/simulators/index-' \
        + xcode_version + '-' + xcode_uuid + '.dvtdownloadableindex'
    try:
        xcode_catalog_path = replicate_url(url, temp_dir, show_progress=False)
    except ReplicationError, err:
        print >> sys.stderr, 'Could not replicate %s: %s' % (url, err)
        exit(-1)
    try:
        catalog = plistlib.readPlist(xcode_catalog_path)
        downloadable_simulators = []
        for simulator in catalog['downloadables']:
            pkg_identifier = simulator['identifier'].split(
                '$(DOWNLOADABLE_VERSION_MAJOR)_$(DOWNLOADABLE_VERSION_MINOR)'
                )[0]
            pkg_version = simulator['version']
            simulator_type = pkg_identifier.split('com.apple.pkg.')[1]
            major_version = pkg_version.split('.')[0]
            minor_version = pkg_version.split('.')[1]
            simulator_version = major_version + '.' + minor_version
            url = 'https://devimages-cdn.apple.com/downloads/xcode/'\
                'simulators/' + pkg_identifier + major_version + '_' + \
                minor_version + '-' + pkg_version + '.dmg'
            if 'TV' in simulator_type:
                simulator_runtime = 'tvOS'
            elif 'iPhone' in simulator_type:
                simulator_runtime = 'iOS'
            elif 'Watch' in simulator_type:
                simulator_runtime = 'watchOS'
            downloadable_simulators.append(
                {
                    'download_url': url,
                    'major_version': major_version,
                    'minor_version': minor_version,
                    'pkg_identifier': pkg_identifier,
                    'pkg_version': pkg_version,
                    'simulator_runtime': simulator_runtime,
                    'simulator_type': simulator_type,
                    'simulator_version': simulator_version
                }
            )
        return downloadable_simulators
    except (OSError, IOError, ExpatError), err:
        print >> sys.stderr, (
            'Error reading %s: %s' % (xcode_catalog_path, err))
        exit(1)


def replicate_package(url, temp_dir):
    try:
        dmg_url = replicate_url(url, temp_dir, show_progress=True)
        return dmg_url
    except ReplicationError, err:
        print >> sys.stderr, (
            'Could not replicate %s: %s' % (package['URL'], err))
        exit(-1)


def mountdmg(dmgpath):
    """
    Attempts to mount the dmg at dmgpath and returns first mountpoint
    """
    mountpoints = []
    dmgname = os.path.basename(dmgpath)
    cmd = ['/usr/bin/hdiutil', 'attach', dmgpath,
           '-mountRandom', '/tmp', '-nobrowse', '-plist',
           '-owners', 'on']
    proc = subprocess.Popen(cmd, bufsize=-1,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (pliststr, err) = proc.communicate()
    if proc.returncode:
        print >> sys.stderr, 'Error: "%s" while mounting %s.' % (err, dmgname)
        return None
    if pliststr:
        plist = plistlib.readPlistFromString(pliststr)
        for entity in plist['system-entities']:
            if 'mount-point' in entity:
                mountpoints.append(entity['mount-point'])

    return mountpoints[0]


def unmountdmg(mountpoint):
    """
    Unmounts the dmg at mountpoint
    """
    proc = subprocess.Popen(['/usr/bin/hdiutil', 'detach', mountpoint],
                            bufsize=-1, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    (dummy_output, err) = proc.communicate()
    if proc.returncode:
        print >> sys.stderr, 'Polite unmount failed: %s' % err
        print >> sys.stderr, 'Attempting to force unmount %s' % mountpoint
        # try forcing the unmount
        retcode = subprocess.call(['/usr/bin/hdiutil', 'detach', mountpoint,
                                   '-force'])
        if retcode:
            print >> sys.stderr, 'Failed to unmount %s' % mountpoint


def create_distribution_package(dxml_path, temp_mount_path, output_dir,
                                pkg_name):
    pkg_file_name = pkg_name + '_dist.pkg'
    pkg_output_path = os.path.join(output_dir, pkg_file_name)
    cmd = ['/usr/bin/productbuild', '--distribution', dxml_path,
           '--resources', '.', pkg_output_path]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, cwd=temp_mount_path)
        output, err = proc.communicate()
        return True
    except subprocess.CalledProcessError, err:
        print >> sys.stderr, err
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--xcodepath', default='/Applications/Xcode.app',
                        help='Required: Path to Xcode app.')
    parser.add_argument('--outputdir', metavar='path_to_working_dir',
                        default='/Users/Shared/makexcodesimulators',
                        help='Path to output packages.')
    args = parser.parse_args()

    xcodepath = args.xcodepath
    outputpath = args.outputdir
    if not os.path.isdir(outputpath):
        os.makedirs(outputpath)

    if not os.path.isdir(xcodepath):
        print 'Xcode path was not found: %s' % xcodepath
        exit(1)
    else:
        global DISTRIBUTIONPLIST
        temp_dir = tempfile.mkdtemp()
        print 'Temporary directory: %s' % str(temp_dir)
        xcode_app_info = get_xcode_info(xcodepath)
        if len(xcode_app_info) == 2:
            xcode_version = xcode_app_info['DTXcode']
            xcode_uuid = xcode_app_info['DVTPlugInCompatibilityUUID']
            downloadable_simulators = download_and_parse_xcode_catalog(
                temp_dir, xcode_version, xcode_uuid)
            sorted_downloadabled_simulators = sorted(downloadable_simulators)
            if not downloadable_simulators:
                print >> sys.stderr, (
                    'No Xcode simulators found in catalog.')
                exit(1)

            # display a menu of choices
            print '%2s %12s %10s  %s' % ('#', 'SimulatorType', 'Version',
                                         'URL')
            for index, simulator_info in enumerate(
                    sorted_downloadabled_simulators):
                print '%2s %12s %10s  %s' % (
                    index+1, simulator_info['simulator_type'],
                    simulator_info['simulator_version'],
                    simulator_info['download_url'])

            answer = raw_input(
                '\nChoose a product to download (1-%s): ' % len(
                    downloadable_simulators))
            try:
                id = int(answer) - 1
                if id < 0:
                    raise ValueError
                simulator_chosen = sorted_downloadabled_simulators[id]
            except (ValueError, IndexError):
                print 'Exiting.'
                exit(0)

            # download the package for the selected product
            simulator_dmg_path = replicate_package(
                simulator_chosen['download_url'], temp_dir)

            # mount the dmg so we can make our new package
            print 'Mounting dmg at: %s' % str(simulator_dmg_path)
            mountpoint = mountdmg(simulator_dmg_path)

            if mountpoint:
                plist_title = simulator_chosen['simulator_type'] + \
                    simulator_chosen['major_version'] + '_' + \
                    simulator_chosen['minor_version']
                plist_pkg_relative_path = plist_title + '.pkg'
                plist_pkg_ref = simulator_chosen['pkg_identifier'] + \
                    simulator_chosen['major_version'] + '_' + \
                    simulator_chosen['minor_version']
                plist_pkg_version = simulator_chosen['pkg_version']
                plist_runtime_path = '/Library/Developer/CoreSimulator/'\
                    'Profiles/Runtimes/%s.simruntime' % (
                        simulator_chosen['simulator_runtime'] + ' ' +
                        simulator_chosen['simulator_version'])
                plist_sdk_version = simulator_chosen['simulator_type'] + \
                    simulator_chosen['major_version'] + '_' + \
                    simulator_chosen['minor_version']

                DISTRIBUTIONPLIST += '\n' + '    '\
                    '<title>\"%s\"</title>' % (plist_title)
                DISTRIBUTIONPLIST += '\n' + '    '\
                    '<pkg-ref id=\"%s\"/>' % (plist_pkg_ref)
                DISTRIBUTIONPLIST += '\n' + '    '\
                    '<options customize=\"allow\"/>'
                DISTRIBUTIONPLIST += '\n' + '    '\
                    '<choices-outline>'
                DISTRIBUTIONPLIST += '\n' + '        '\
                    '<line choice=\"%s\"/>' % (plist_pkg_ref)
                DISTRIBUTIONPLIST += '\n' + '    '\
                    '</choices-outline>'
                DISTRIBUTIONPLIST += '\n' + '    '\
                    '<choice id=\"%s\" visible=\"true\" title=\"%s\" '\
                    'customLocation="%s">' % (plist_pkg_ref, plist_sdk_version,
                                              plist_runtime_path)
                DISTRIBUTIONPLIST += '\n' + '        '\
                    '<pkg-ref id=\"%s\"/>' % (plist_pkg_ref)
                DISTRIBUTIONPLIST += '\n' + '    '\
                    '</choice>'
                DISTRIBUTIONPLIST += '\n' + '    '\
                    '<pkg-ref id=\"%s\" version=\"%s\" '\
                    'onConclusion="none">%s</pkg-ref>' % (
                        plist_pkg_ref, plist_pkg_version,
                        plist_pkg_relative_path)
                DISTRIBUTIONPLIST += '\n' + '</installer-gui-script>'

                print 'Creating Distribution plist...'

                distribution_plist_path = os.path.join(temp_dir, 'dist.xml')
                with open(distribution_plist_path, 'wb') as f:
                    f.write(DISTRIBUTIONPLIST)

                print 'Creating new distribution package...'
                pkg_created = create_distribution_package(
                    distribution_plist_path, mountpoint, outputpath,
                    plist_title)

                if pkg_created:
                    print 'Package successfully created...'
                else:
                    print 'Package build failed...'

                print 'Unmounting original dmg...'
                unmountdmg(mountpoint)

                print 'Cleaning up...'
                shutil.rmtree(temp_dir)

        else:
            print 'Could not obtain all of the keys from Xcode!'
            exit(1)


if __name__ == '__main__':
    main()
