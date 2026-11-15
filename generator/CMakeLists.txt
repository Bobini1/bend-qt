cmake_minimum_required(VERSION 3.25)
project(bend_qt_extractor LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(BQT_QT_VERSION "6.12.0" CACHE STRING "Exact Qt/PySide release to bind")
file(READ "${CMAKE_CURRENT_SOURCE_DIR}/qt_targets.json" BQT_TARGETS)
string(JSON BQT_SHIBOKEN_PIN ERROR_VARIABLE BQT_PIN_ERROR GET "${BQT_TARGETS}" "${BQT_QT_VERSION}" shiboken_commit)
if(BQT_PIN_ERROR)
    message(FATAL_ERROR "No reviewed Qt/PySide build target for ${BQT_QT_VERSION}")
endif()
string(JSON BQT_EXTRACTOR_SOURCE GET "${BQT_TARGETS}" "${BQT_QT_VERSION}" extractor_source)
find_package(Qt6 ${BQT_QT_VERSION} EXACT REQUIRED COMPONENTS Core)
string(REGEX MATCH "^[0-9]+\\.[0-9]+" BQT_QT_API_VERSION "${BQT_QT_VERSION}")
qt_standard_project_setup(REQUIRES ${BQT_QT_API_VERSION})

set(SHIBOKEN_SOURCE "" CACHE PATH "Pinned pyside-setup checkout for the selected Qt release")
if(NOT EXISTS "${SHIBOKEN_SOURCE}/${BQT_EXTRACTOR_SOURCE}/apiextractor.h")
    message(FATAL_ERROR "Set SHIBOKEN_SOURCE to the pinned pyside-setup ${BQT_QT_VERSION} checkout")
endif()
find_package(Git REQUIRED)
execute_process(
    COMMAND "${GIT_EXECUTABLE}" -C "${SHIBOKEN_SOURCE}" rev-parse HEAD
    OUTPUT_VARIABLE BQT_SHIBOKEN_COMMIT
    OUTPUT_STRIP_TRAILING_WHITESPACE
    COMMAND_ERROR_IS_FATAL ANY
)
if(NOT BQT_SHIBOKEN_COMMIT STREQUAL BQT_SHIBOKEN_PIN)
    message(FATAL_ERROR "Use the pinned Shiboken ${BQT_QT_VERSION} source commit ${BQT_SHIBOKEN_PIN}")
endif()
find_path(CLANG_INCLUDE_DIRS clang-c/Index.h HINTS /usr/lib/llvm-19/include REQUIRED)
find_library(CLANG_LIBRARY NAMES clang-19 clang HINTS /usr/lib/llvm-19/lib REQUIRED)
add_library(libclang SHARED IMPORTED)
set_target_properties(libclang PROPERTIES IMPORTED_LOCATION "${CLANG_LIBRARY}")
set(BUILD_TESTS OFF)
set(CMAKE_DISABLE_FIND_PACKAGE_LibXml2 TRUE)
set(CMAKE_DISABLE_FIND_PACKAGE_LibXslt TRUE)
add_subdirectory(
    "${SHIBOKEN_SOURCE}/${BQT_EXTRACTOR_SOURCE}"
    apiextractor
)
find_program(LLVM_CONFIG NAMES llvm-config-19 REQUIRED)
execute_process(
    COMMAND "${LLVM_CONFIG}" --version
    OUTPUT_VARIABLE BQT_LLVM_VERSION
    OUTPUT_STRIP_TRAILING_WHITESPACE
    COMMAND_ERROR_IS_FATAL ANY
)
string(REGEX MATCH "^[0-9]+" BQT_LLVM_MAJOR "${BQT_LLVM_VERSION}")
target_compile_definitions(apiextractor PRIVATE LLVM_VERSION=${BQT_LLVM_MAJOR})
qt_add_executable(bend-qt-extract main.cpp)
target_include_directories(bend-qt-extract PRIVATE
    "${SHIBOKEN_SOURCE}/${BQT_EXTRACTOR_SOURCE}"
)
target_compile_definitions(bend-qt-extract PRIVATE
    BQT_SHIBOKEN_VERSION="${BQT_QT_VERSION}"
    BQT_SHIBOKEN_COMMIT="${BQT_SHIBOKEN_PIN}"
    BQT_QT_API_VERSION="${BQT_QT_API_VERSION}"
)
target_link_libraries(bend-qt-extract PRIVATE apiextractor Qt6::Core)

