# Community forum — reply to post #3 (@tzsolt)

> Target: <https://community.home-assistant.io/t/control-dooya-rf433-blinds-with-esp32-cc1101-via-esphome/984671/3>
> Posted 2026-03-04, never answered. Post as a reply to #3.
>
> Two things to get out of it: his ESP32-S3 YAML (he said it needed a special
> config and never shared it), and closing the loop on the BIDI motor before
> he sinks a weekend into it.

---

Hey, sorry, this one slipped past me for far too long.

Two separate things in your message, so let me take them one at a time.

**The ESP32-S3.** Great to know it works there, that comes up regularly. You
mentioned it needs a special YAML configuration — could you paste yours? Even
just the `esp32:` and pin blocks would help. I only ever tested this on a plain
DevKit v1, so I have nothing useful to say to the next person who shows up with
an S3, and right now your post is the only evidence in the thread that it works
at all. I'll link it from the original post once it's here.

**The BIDI motor.** This is where I'd rather be honest than encouraging: I don't
think you'll get there with this setup. The one-way Dooya protocol my DC90
remotes speak — the one `transmit_dooya` encodes — is not what a bidirectional
motor is listening for. It expects a two-way exchange with acknowledgements, so
brute-forcing pairing codes with a one-way transmitter won't get a response.

It's very likely the same wall @kamerat hit in post #4 with a Motionblinds
CMD-02-P (my answer is in post #8). As far as I know the Motionblinds hardware
is Dooya-built, which would make your BIDI motor and their CMD-02-P the same
family — same protocol, same problem. If that's right, the realistic path is the
official Motionblinds integration with their WiFi bridge, which people report
working well, rather than a CC1101.

If you do want to poke at it anyway, one thing has improved since March: the
`cc1101` component is now in ESPHome core (since 2025.12,
<https://esphome.io/components/cc1101.html>) and it has a packet mode with an
`on_packet` trigger. That gets you raw frames even when no protocol decoder
recognises them, which is the right starting point for reverse engineering
something the `dooya` dumper can't read. I'd genuinely like to be proven wrong
here — nobody seems to have decoded that protocol publicly yet, and if you get
anywhere I'll link it from the original post.
