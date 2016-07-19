## APInfo

APInfo allows you to obtain information about iOS/macOS applications and optionally output the results to slack.

### Commands
```
Usage: APInfo [options]

Options:
  -h, --help            show this help message and exit
  --id=ID               Required: iTunes Application ID.
  --expectedversion=EXPECTEDVERSION
                        Optional: Specify expected version. Useful when using
                        Slack output.
  --releasedate         Optional: Obtain Release Date information
  --releasenotes        Optional: Obtain Release Notes information.
  --slack               Optional: Use Slack
  --slackwebhook=SLACKWEBHOOK
                        Optional: Slack Webhook URL. Requires Slack Option.
  --slackusername=SLACKUSERNAME
                        Optional: Slack username. Requires Slack Option.
  --slackchannel=SLACKCHANNEL
                        Optional: Slack channel. Requires Slack Option.
  --version             Optional: Obtain Version information.
```
### Examples
##### Application Info
At the bare minimum, the `id` for the Application must be passed.

Example:
```
Application: Keynote for macOS
URL: https://itunes.apple.com/us/app/keynote/id409183694?mt=12
ID: 409183694

./APInfo \
--id 409183694
Application: Keynote (macOS)
```

##### Additional Application Info
APInfo can optionally return the Release Date, Release Notes and version of the application.

Example:
```
./APInfo \
--id 409183694 \
--releasedate \
--releasenotes \
--version

Application: Keynote (macOS)
Version: 6.6.2
Release Date: 2016-05-10
Release Notes: This update contains stability improvements and bug fixes.
```
##### Expected Version
If you plan to wrap APInfo with another tool, you may want to pass an expected version. This is useful for integrating with Slack to reduce the number of POSTS.

Example:
```
./APInfo \
--id 409183694 \
--expectedversion "6.6.2"

Found expected version for Application: Keynote (macOS). Exiting.
```

##### Uploading to Slack
If you would like to optionally upload your results to slack, you must pass _all_ slack parameters:

A webhook is also required. For more information, please see [Slack's documentation](https://api.slack.com/incoming-webhooks).
```
./APInfo \
--id 409183694 \
--releasedate \
--releasenotes \
--version \
--slack \
--slackchannel "#test" \
--slackusername "APInfo" \
--slackwebhook "https://hooks.slack.com/services/yourwebhookurl"
```

The slack output will conditionally use the Application's 100px icon for the bot's icon_url.

![APInfo Slack Example](https://github.com/erikng/scripts/raw/master/APInfo/APInfo.png)

##### Additional notes on Slack
If you plan to wrap this application, note that there is a bug with Slack where only the first message from a bot will show the icon. To workaround this, conditionally or statically set the `--slackusername` to unique values per application.
