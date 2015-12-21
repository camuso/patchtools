# .bashrc

# Source global definitions
if [ -f /etc/bashrc ]; then
	. /etc/bashrc
fi

#export CLICOLOR=1
#export LSCOLORS=DxGxcxdxCxegedabagacad

[ $(echo $PATH | grep -w $HOME/bin) ] || export PATH=$PATH:$HOME/bin

export TEMPDIR=~/Maildir/temp/
export PRJDIR=../foo
export HISTCONTROL=ignoredups

#echo $LS_COLORS > old_colors
LS_COLORS='no=00:fi=00:di=01;93:ln=00;36:pi=40;33:so=01;95:bd=40;33;01:cd=40;33;01:tw=01;04;33:ow=01;04;35:or=01;05;37;41:mi=01;05;37;41:ex=01;32:*.cmd=01;32:*.exe=01;32:*.com=01;32:*.btm=01;32:*.bat=01;32:*.sh=01;32:*.csh=01;32:*.tar=01;31:*.tgz=01;31:*.svgz=01;31:*.arj=01;31:*.taz=01;31:*.lzh=01;31:*.lzma=01;31:*.zip=01;31:*.z=01;31:*.Z=01;31:*.dz=01;31:*.gz=01;31:*.bz2=01;31:*.tbz2=01;31:*.bz=01;31:*.tz=01;31:*.deb=01;31:*.rpm=01;31:*.jar=01;31:*.rar=01;31:*.ace=01;31:*.zoo=01;31:*.cpio=01;31:*.7z=01;31:*.rz=01;31:*.jpg=01;95:*.jpeg=01;95:*.gif=01;95:*.bmp=01;95:*.pbm=01;95:*.pgm=01;95:*.ppm=01;95:*.tga=01;95:*.xbm=01;95:*.xpm=01;95:*.tif=01;95:*.tiff=01;95:*.png=01;95:*.mng=01;95:*.pcx=01;95:*.mov=01;95:*.mpg=01;95:*.mpeg=01;95:*.m2v=01;95:*.mkv=01;95:*.ogm=01;95:*.mp4=01;95:*.m4v=01;95:*.mp4v=01;95:*.vob=01;95:*.qt=01;95:*.nuv=01;95:*.wmv=01;95:*.asf=01;95:*.rm=01;95:*.rmvb=01;95:*.flc=01;95:*.avi=01;95:*.fli=01;95:*.gl=01;95:*.dl=01;95:*.xcf=01;95:*.xwd=01;95:*.yuv=01;95:*.svg=01;95:'
export LS_COLORS

# export GREP_COLORS='ms=01;31:mc=01;31:sl=:cx=:fn=01;32:ln=01;32:bn=32:se=36'
export GREP_COLORS='ms=01;31:mc=01;31:sl=:cx=:fn=95:ln=32:bn=32:se=36'

export PS1="[\u\[\e[31;1m\]@\[\e[1;32m\]\h \[\e[1;33m\]\W\[\e[0m\]]\$ "

# User specific aliases and functions
#
alias rm='rm -i'
alias mv='mv -i'
alias cp='cp -iv'

function today {
	echo "Today's date is:"
	date +"%A, %B %-d, %Y"
}
alias alf='ls -alFch'
# alias lsd='ls -ald  */ .*/'
alias searchdown='perl /usr/bin/searchdown.pl'
alias mntiso='mount -o loop -t iso9660'
alias gitampatch='rlwrap gitampatch'
alias rold='pushd +1'
alias rord='pushd -1'
alias vboxmanage='/usr/lib/virtualbox/VBoxManage'
alias rsyncp='rsync -Pvat -e "ssh -o 'StrictHostKeyChecking=no' -o 'UserKnownHostsFile=/dev/null'"'
alias grep="grep --color"

# Need to get the grep version, because earlier versions do not support
# the '-T' option.
#
# The minimum version supporting the '-T' option is 2.6.0
#
mingrepversion=260

# Get the first line of the grep version and trim out everything but the
# version number.
#
grepversion=$(grep -V | head -1 | tr -cd '[[:digit:]]')

# If the grepversion is 2.6.0 or greater, then it supports '-T', initial tabs
#
if [ $grepversion -ge $mingrepversion ]; then tabs='T'; else tabs=''; fi

alias grap="grep --color -Hn$tabs"

# grep ignoring case (i), ignoring binaries (I), print filenames (H),
# and skip other file systems.
#
alias grip='grep -iIHr -D skip --color'

# ssh with no key checking and no known_hosts file
#
alias ssh="ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"

[ -e /usr/bin/vimx ] && alias vim='/usr/bin/vimx'

# No ttyctl, so we need to save and then restore terminal settings
vim(){
    local STTYOPTS="$(stty --save)"
    stty stop '' -ixoff
    command vim "$@"
    stty "$STTYOPTS"
}

lsd(){
    [ "$1" ] && cd $1;
    ls --color=auto -ald */ .*/;
    [ "$1" ] && cd -
}

# Also ... find . ! -name . -prune -type f
lsf(){
	[ "$1" ] && cd $1;
	ls -alFch | grep --color ^[^d];
	[ "$1" ] && cd -;
}

comment2commits(){
	echo "comment2commits source-dir dest-file"
	source ~/bin/lib/ui.source;
	source ~/bin/lib/gitutilities.source;
	git_comment2commitsfile "$1" "$2";
}