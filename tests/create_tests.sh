#!/bin/sh

# Skript na vytvorenie súborov test[i].in, test[i].out, test[i].rc
# s predvolenou hodnotou 0 v test[i].rc.
# Usage: ./create_tests.sh <start> <end>

if [ $# -ne 2 ]; then
  echo "Usage: $0 <start> <end>"
  exit 1
fi

start=$1
end=$2

# Pre každý test i v rozsahu <start>.. <end>
for i in $(seq $start $end); do
  for ext in in out rc; do
    filename="test${i}.${ext}"
    # Ak súbor existuje, preskočíme ho
    if [ -e "$filename" ]; then
      echo "$filename already exists, skipping."
    else
      echo "Creating $filename..."
      # Súbor .rc dostane predvolene '0'
      if [ "$ext" = "rc" ]; then
        echo "0" > "$filename"
      else
        # .in a .out vytvoríme prázdne
        touch "$filename"
      fi
    fi
  done
done
