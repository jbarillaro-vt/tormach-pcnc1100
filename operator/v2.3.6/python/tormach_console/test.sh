#!/bin/sh

# cd into directory script is run from
cd "$(dirname "$(realpath "$0")")";

halrun -f ./test.hal
