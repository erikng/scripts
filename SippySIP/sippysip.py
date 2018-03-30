#!/usr/bin/python
# -*- coding: utf-8 -*-

# Sippy SIP - python wrapper for csrutil
# User notifications designed around Yo

# Written by Erik Gomez
from SystemConfiguration import SCDynamicStoreCopyConsoleUser
import datetime
import os
import platform
import plistlib
import shutil
import subprocess
import time

# Global Variables
# Make sure sippysipLAId variables matches the <key>Label</key> in the
# sippySIPLaunchAgent variable
sippysipLAId = 'com.github.erikng.sippysipagent'
# Path to the plist sippysip writes to track each time there is an event
# where sippysip had to fix the device.
writePlistPath = '/Library/Application Support/LogEvents/sippysip.plist'


sippySIPLaunchAgent = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.github.erikng.sippysipagent</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python</string>
        <string>/Library/Application Support/sippysip/sippysipagent.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
"""


sippySIPAgentScript = """#!/usr/bin/python
# -*- coding: utf-8 -*-
import subprocess

# Path to Yo binary
yopath = '/Applications/Utilities/yo.app/Contents/MacOS/yo'

def yo_single_button(yopath, title, informtext, accepttext, declinetext,
    script):
    try:
        cmd = [
            yopath,  # path to you
            '-t', title,  # title
            '-n', informtext,  # subtext
            '-b', accepttext,  # accept button
            '-B', script,  # accept button script action
            '-o', declinetext,  # decline button
            '-d'  # ignore do-not-disturb mode
            ]
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output, err = proc.communicate()
        return output
    except Exception:
        return None


def touch(path):
    try:
        touchFile = ['/usr/bin/touch', path]
        proc = subprocess.Popen(touchFile, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        touchFileOutput, err = proc.communicate()
        os.chmod(path, 0777)
        return touchFileOutput
    except Exception:
        return None


def main():
    # Send a yo notification
    global yopath
    yo_single_button(yopath, 'Mind rebooting?', 'We detected that your device '
    'is in a misconfigured state.', 'Restart Now', 'Restart Later',
    r\"\"\"osascript -e \'tell app "loginwindow" to «event aevtrrst»\'\"\"\")

    # Touch our sippysip watch path.
    touch('/Users/Shared/.sippysip')


if __name__ == '__main__':
    main()

"""


def cleanUp(sippysipPath, sippysipLAPath, sippysipLAId, userId,
            sippysipWatchPath):
    # Attempt to remove the LaunchAgent
    SippySIPLog('Attempting to remove LaunchAgent: ' + sippysipLAPath)
    try:
        os.remove(sippysipLAPath)
    except:  # noqa
        pass

    # Attempt to remove the trigger
    if os.path.isfile(sippysipWatchPath):
        SippySIPLog('Attempting to remove trigger: ' + sippysipWatchPath)
        try:
            os.remove(sippysipWatchPath)
        except:  # noqa
            pass

    # Attempt to remove the launchagent from the user's list
    SippySIPLog('Targeting user id for LaunchAgent removal: ' + userId)
    SippySIPLog('Attempting to remove LaunchAgent: ' + sippysipLAId)
    launchCTL('/bin/launchctl', 'asuser', userId,
              '/bin/launchctl', 'remove', sippysipLAId)

    # Attempt to kill SippySIP's path
    SippySIPLog('Attempting to remove sippysip directory: ' + sippysipPath)
    try:
        shutil.rmtree(sippysipPath)
    except:  # noqa
        pass


def getConsoleUser():
    CFUser = SCDynamicStoreCopyConsoleUser(None, None, None)
    return CFUser


def launchCTL(*arg):
    # Use *arg to pass unlimited variables to command.
    cmd = arg
    run = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output, err = run.communicate()
    return output


def csrutil(command):
    cmd = ['/usr/bin/csrutil', command]
    run = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output, err = run.communicate()
    if command == 'status':
        if 'System Integrity Protection status: disabled.' in output:
            return True
        else:
            return False
    elif command == 'clear':
        if 'Successfully cleared System Integrity Protection.' in output:
            return True
        else:
            return False


def nvram():
    cmd = ['/usr/sbin/nvram', '-p']
    run = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output, err = run.communicate()
    if 'csr-active-config' in output:
        return True
    else:
        return False


def writePlist(timestamp, writePlistPath):
    sippysip = {'Events': []}
    if os.path.isfile(writePlistPath):
        sippysip = plistlib.readPlist(writePlistPath)
        sippysip['Events'].append(str(timestamp))
        plistlib.writePlist(sippysip, writePlistPath)
    else:
        sippysip['Events'].append(str(timestamp))
        plistlib.writePlist(sippysip, writePlistPath)


def getOSVersion():
    """Return OS version."""
    return platform.mac_ver()[0]


def SippySIPLog(text):
    logPath = '/private/var/log/sippysip.log'
    formatStr = '%b %d %Y %H:%M:%S %z: '
    logevent = time.strftime(formatStr) + text
    print logevent
    with open(logPath, 'a+') as log:
        log.write(logevent + '\n')


def main():
    # State variables
    global sippySIPLaunchAgent
    global sippySIPAgentScript
    global sippysipLAId
    global writePlistPath
    currentUserUid = getConsoleUser()
    userId = str(getConsoleUser()[1])
    pendingReboot = False

    # Check SIP Status
    SippySIPLog('Checking SIP State...')
    sipCsrutilDisabled = csrutil('status')
    SippySIPLog('Checking NVRAM SIP State...')
    sipNVRAMDisabled = nvram()

    # If SIP is disabled, we need to do $things.
    if sipCsrutilDisabled:
        SippySIPLog('Detected SIP Disabled via csrutil. Checking against '
                    'NVRAM entries...')
        if sipNVRAMDisabled:
            SippySIPLog('Detected SIP Disabled via NVRAM.')
            SippySIPLog('Attempting to Re-Enable SIP...')
            sipCsrutilClear = csrutil('clear')
            if sipCsrutilClear:
                SippySIPLog('SIP Re-Enabled - Logging event to plist.')
                timestamp = datetime.datetime.utcnow()
                sippysipPlist = writePlist(timestamp, writePlistPath)
                pendingReboot = True
        else:
            SippySIPLog('Detected SIP Enabled via NVRAM. Device pending '
                        'reboot...')
            pendingReboot = True
    # If csrutil says things are cool, let's just validate against NVRAM.
    else:
        SippySIPLog('Detected SIP Enabled via csrutil. Checking against '
                    'NVRAM entries...')
        # Some kind of fuckery is going on here, so let's clear it and log.
        if sipNVRAMDisabled:
            SippySIPLog('Detected SIP Disabled via NVRAM.')
            SippySIPLog('Attempting to Re-Enable SIP...')
            sipCsrutilClear = csrutil('clear')
            if sipCsrutilClear:
                SippySIPLog('SIP Re-Enabled - Logging event to plist.')
                timestamp = datetime.datetime.utcnow()
                sippysipPlist = writePlist(timestamp, writePlistPath)
                pendingReboot = True
        else:
            SippySIPLog('SIP has been validated and is enabled.')
            exit(0)

    # If we are pending reboot, we should send a Yo notification to the user
    # informing them that it's time to reboot.
    if pendingReboot:
        SippySIPLog('Device is pending reboot - triggering user alert.')
        if (currentUserUid[0] is None or currentUserUid[0] == u'loginwindow'
                or currentUserUid[0] == u'_mbsetupuser'):
            SippySIPLog('No user logged in - Skipping Yo notification...')
        else:
            # sippysip's agent variables
            sippysipLAPlist = sippysipLAId + '.plist'
            sippysipPath = os.path.join('/Library', 'Application Support',
                                        'sippysip')
            sippysipAgentPath = os.path.join(sippysipPath, 'sippysipagent.py')
            sippysipLAPath = os.path.join('/Library', 'LaunchAgents',
                                          sippysipLAPlist)
            sippysipWatchPath = '/Users/Shared/.sippysip'

            # Create sippysip's agent folder, script and agent.
            SippySIPLog('Creating sippysip agent folder and files...')
            if not os.path.isdir(sippysipPath):
                os.makedirs(sippysipPath)
            with open(sippysipAgentPath, 'wb') as na:
                na.write(sippySIPAgentScript)
            with open(sippysipLAPath, 'wb') as la:
                la.write(sippySIPLaunchAgent)

            # Turn on sippysip's agent
            SippySIPLog('Loading sippysip agent...')
            launchCTL('/bin/launchctl', 'asuser', userId,
                      '/bin/launchctl', 'load', sippysipLAPath)

            # Wait for sippysip's agent to complete
            while not os.path.isfile(sippysipWatchPath):
                SippySIPLog('Waiting for the trigger file...')
                time.sleep(0.5)

            # Clean this shit up.
            SippySIPLog('Cleaning up sippysip agent folder and files...')
            cleanUp(sippysipPath, sippysipLAPath, sippysipLAId, userId,
                    sippysipWatchPath)


if __name__ == '__main__':
    main()
