#!/usr/bin/env bash
set -euo pipefail

DRY_RUN=0
CONTAINER_BUILD=0
PREFIX="${HT_SOLVER_PREFIX:-"$PWD/.hubble_tension_solvers"}"
IMAGE="${HT_SOLVER_IMAGE:-hubble-tension-solvers:phase10}"
CONTAINER_RUNTIME="${HT_SOLVER_CONTAINER_RUNTIME:-${HT_LAB_SANDBOX_RUNTIME:-podman}}"
CC_BIN="${HT_SOLVER_CC:-gcc-13}"
OPENMP="${HT_SOLVER_OPENMP:-libgomp}"
BLAS="${HT_SOLVER_BLAS:-openblas}"
PYTHON_BIN="${PYTHON:-python3}"

CLASS_REF_DEFAULT="e85808324f51fc694d12e3ed7439552a3c3f9540"
CLASS_EDE_REF_DEFAULT="5a131c91d657dd9a7c6364cc45b038710f8d0d97"
AXICLASS_REF_DEFAULT="ba4ede7b1d735aa6312ab5f4355d26b5e617e70c"
HYREC2_REF_DEFAULT="09e8243d0e08edd3603a94dfbc445ae06cafe139"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --container-build)
      CONTAINER_BUILD=1
      shift
      ;;
    --prefix)
      PREFIX="$2"
      shift 2
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 64
      ;;
  esac
done

run() {
  if [[ "$DRY_RUN" == "1" ]]; then
    printf '+ %q' "$@"
    printf '\n'
  else
    "$@"
  fi
}

resolve_ref() {
  local env_name="$1"
  local default_ref="$2"
  local value="${!env_name:-}"
  if [[ -n "$value" ]]; then
    printf '%s' "$value"
    return
  fi
  if [[ "${HT_SOLVER_DISABLE_DEFAULT_PINS:-0}" != "1" && -n "$default_ref" ]]; then
    printf '%s' "$default_ref"
    return
  fi
  if [[ "$DRY_RUN" == "1" ]]; then
    printf '<required:%s>' "$env_name"
    return
  fi
  echo "bootstrap_solver_unavailable: $env_name must pin a solver ref before a real build" >&2
  exit 42
}

clone_solver() {
  local name="$1"
  local repo="$2"
  local ref_env="$3"
  local default_ref="$4"
  local ref
  ref="$(resolve_ref "$ref_env" "$default_ref")"
  run mkdir -p "$PREFIX/src"
  run git clone --depth 1 "$repo" "$PREFIX/src/$name"
  run git -C "$PREFIX/src/$name" fetch --depth 1 origin "$ref"
  run git -C "$PREFIX/src/$name" checkout "$ref"
}

build_class_family() {
  local name="$1"
  run make -C "$PREFIX/src/$name" CC="$CC_BIN" OMP="$OPENMP" BLAS="$BLAS" -j "${HT_SOLVER_JOBS:-2}"
}

build_hyrec2() {
  run make -C "$PREFIX/src/hyrec2" CC="$CC_BIN" -j "${HT_SOLVER_JOBS:-2}"
}

container_build() {
  local class_ref class_ede_ref axiclass_ref hyrec2_ref
  class_ref="$(resolve_ref "HT_CLASS_REF" "$CLASS_REF_DEFAULT")"
  class_ede_ref="$(resolve_ref "HT_CLASS_EDE_REF" "$CLASS_EDE_REF_DEFAULT")"
  axiclass_ref="$(resolve_ref "HT_AXICLASS_REF" "$AXICLASS_REF_DEFAULT")"
  hyrec2_ref="$(resolve_ref "HT_HYREC2_REF" "$HYREC2_REF_DEFAULT")"
  run "$CONTAINER_RUNTIME" build \
    -f tools/Containerfile.solvers \
    --build-arg "HT_CLASS_REF=$class_ref" \
    --build-arg "HT_CLASS_EDE_REF=$class_ede_ref" \
    --build-arg "HT_AXICLASS_REF=$axiclass_ref" \
    --build-arg "HT_HYREC2_REF=$hyrec2_ref" \
    -t "$IMAGE" \
    .
}

echo "solver build plan: image=$IMAGE prefix=$PREFIX container_runtime=$CONTAINER_RUNTIME compiler=$CC_BIN openmp=$OPENMP blas=$BLAS python=$PYTHON_BIN"

if [[ "$CONTAINER_BUILD" == "1" ]]; then
  container_build
  echo "solver container build complete: $IMAGE"
  exit 0
fi

clone_solver "class" "https://github.com/lesgourg/class_public.git" "HT_CLASS_REF" "$CLASS_REF_DEFAULT"
clone_solver "class_ede" "https://github.com/mwt5345/class_ede.git" "HT_CLASS_EDE_REF" "$CLASS_EDE_REF_DEFAULT"
clone_solver "axiclass" "https://github.com/PoulinV/AxiCLASS.git" "HT_AXICLASS_REF" "$AXICLASS_REF_DEFAULT"
clone_solver "hyrec2" "https://github.com/nanoomlee/HYREC-2.git" "HT_HYREC2_REF" "$HYREC2_REF_DEFAULT"

build_class_family "class"
build_class_family "class_ede"
build_class_family "axiclass"
build_hyrec2

run "$PYTHON_BIN" -m pip install --no-deps "$PREFIX/src/class/python"
run "$PYTHON_BIN" -m pip install --no-deps "$PREFIX/src/class_ede/python"
run "$PYTHON_BIN" -m pip install --no-deps "$PREFIX/src/axiclass/python"

echo "solver build complete: $PREFIX"
