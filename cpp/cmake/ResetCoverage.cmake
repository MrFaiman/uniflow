# Discard counters from previous runs so each report measures the current suite.
file(GLOB_RECURSE coverage_data
    "${BUILD_DIR}/CMakeFiles/*.gcda"
    "${BUILD_DIR}/tests/CMakeFiles/*.gcda"
)
if(coverage_data)
    file(REMOVE ${coverage_data})
endif()
