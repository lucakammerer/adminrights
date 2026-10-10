# Load the scouting logins and local model variables: source dev-env.sh
# Needs `atira models proxy` running in another terminal for QWEN_/CLEF_ calls.
export PATH="$HOME/.local/bin:$PATH"
_atira_env=$(atira scout --env 2>/dev/null) || _atira_env=$(NODE_OPTIONS=--dns-result-order=ipv4first atira scout --env)
eval "$_atira_env" && echo "Scouting env loaded: $(echo "$CHALLENGE_SITE_ACCESS" | grep -o '"siteId":"[^"]*"' | cut -d'"' -f4 | tr '\n' ' ')"
unset _atira_env
