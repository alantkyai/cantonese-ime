cmake_minimum_required(VERSION 3.20)
project(CantoneseImeNativeTestHost LANGUAGES CXX)

if(NOT WIN32 OR NOT CMAKE_SIZEOF_VOID_P EQUAL 8)
  message(FATAL_ERROR "The native acceptance host must be built for Windows AMD64.")
endif()

add_executable(CantoneseImeNativeTestHost WIN32 testhost.cpp ../tsf/tsf_guids.cpp)
target_compile_features(CantoneseImeNativeTestHost PRIVATE cxx_std_17)
target_compile_definitions(CantoneseImeNativeTestHost PRIVATE
  UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX _WIN32_WINNT=0x0601)
target_link_libraries(CantoneseImeNativeTestHost PRIVATE
  user32 gdi32 ole32 oleaut32 uuid comctl32 shell32)
if(MSVC)
  target_compile_options(CantoneseImeNativeTestHost PRIVATE /W4 /EHsc /utf-8)
else()
  target_compile_options(CantoneseImeNativeTestHost PRIVATE -Wall -Wextra)
  target_link_options(CantoneseImeNativeTestHost PRIVATE -static -municode)
endif()
