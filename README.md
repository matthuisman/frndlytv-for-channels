# Frndly TV for Channels

This simple Docker image will generate an M3U playlist optimized for use in [Channels](https://getchannels.com) and expose them over HTTP.

[Channels](https://getchannels.com) supports [custom channels](https://getchannels.com/docs/channels-dvr-server/how-to/custom-channels/) by utilizing streaming sources via M3U playlists.

[Channels](https://getchannels.com) allows for [additional extended metadata tags](https://getchannels.com/docs/channels-dvr-server/how-to/custom-channels/#channels-extensions) in M3U playlists that allow you to give it extra information and art to make the experience better. This project adds those extra tags to make things look great in Channels.

## Set Up

Running the container is easy. Fire up the container as usual. You can set which port it runs on.

    docker run -d --restart unless-stopped --name frndlytv-for-channels -p 8183:80 --env "USERNAME=MY_EMAIL" --env "PASSWORD=MY_PASSWORD" matthuisman/frndlytv-for-channels

Replace `MY_EMAIL` and `MY_PASSWORD` with your Frndly TV login details

By default, the image will use your IP location to fetch streams for your location.  
If you want streams for a different location or your location is not supported,  
simply pass an `IP` environemnt variable to the container with the IP address you want to use.  

    docker run -d --restart unless-stopped --name frndlytv-for-channels -p 8183:80 --env "USERNAME=MY_EMAIL" --env "PASSWORD=MY_PASSWORD" --env "IP=72.229.28.185" matthuisman/frndlytv-for-channels

The above using `72.229.28.185` will get streams for Manhattan, New York.

You can retrieve the playlist URL via the status page.

    http://127.0.0.1:8183

## Add Source to Channels

Once you have your the container running, you can use it with [custom channels](https://getchannels.com/docs/channels-dvr-server/how-to/custom-channels/) in the [Channels](https://getchannels.com) app.

Add a new source in Channels DVR Server and choose `M3U Playlist`.  
Fill out the form using your new playlist URL from above.

Leave the EPG field blank.  
The playlist uses Gracenote IDs which will make [Channels](https://getchannels.com) automatically fetch the EPG.

## License

MIT
