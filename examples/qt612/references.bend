import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expect_error(-A: Type, result: Result<&1, &1, U32 & String, A>, expected: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Wrong error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected checked reference error")

def color_result(value: Qt.Outputs_Int32_Int32_Int32_Int32) -> Qt.Action(Unit):
  match value:
    case Qt.Outputs_Int32_Int32_Int32_Int32{r, g, b, a}:
      require(U32.is_eq(Qt.Int32.word(r), 17) && U32.is_eq(Qt.Int32.word(g), 41) && U32.is_eq(Qt.Int32.word(b), 93) && U32.is_eq(Qt.Int32.word(a), 127), "Scalar output pointers lost order or values")

def color(value: Qt.QColor) -> Qt.Action(Unit):
  Qt.Outputs_Int32_Int32_Int32_Int32.with(Unit, Qt.QColor.getRgb(value), color_result)

def rect_result(value: Qt.Outputs_Int32_Int32_Int32_Int32) -> Qt.Action(Unit):
  match value:
    case Qt.Outputs_Int32_Int32_Int32_Int32{x, y, width, height}:
      require(U32.is_eq(Qt.Int32.word(x), 4294967293) && U32.is_eq(Qt.Int32.word(y), 9) && U32.is_eq(Qt.Int32.word(width), 20) && U32.is_eq(Qt.Int32.word(height), 30), "Signed rectangle outputs changed")

def rect(value: Qt.QRect) -> Qt.Action(Unit):
  Qt.Outputs_Int32_Int32_Int32_Int32.with(Unit, Qt.QRect.getRect(value), rect_result)

def number_result(expected: U32, valid: Bool, value: Qt.Outputs_Int32_Bool) -> Qt.Action(Unit):
  match value:
    case Qt.Outputs_Int32_Bool{number, ok}:
      require(U32.is_eq(Qt.Int32.word(number), expected) && Bool.not(Bool.xor(ok, valid)), "Native return/output pointer combination changed")

def number(value: Qt.QByteArray) -> Qt.Action(Unit):
  Qt.Outputs_Int32_Bool.with(Unit, Qt.QByteArray.toInt(value, Qt.Int32{10}), result => number_result(42, True{}, result))

def invalid_number(value: Qt.QByteArray) -> Qt.Action(Unit):
  Qt.Outputs_Int32_Bool.with(Unit, Qt.QByteArray.toInt(value, Qt.Int32{10}), result => number_result(0, False{}, result))

def inverse_result(value: Qt.Outputs_QTransform_Bool) -> Qt.Action(Unit):
  match value:
    case Qt.Outputs_QTransform_Bool{inverse, ok}:
      do Qt.Action<Unit>:
        identity: Bool <- Qt.QTransform.isIdentity(inverse)
        require(ok && identity, "Owning value plus output pointer failed")

def fail_inverse(value: Qt.Outputs_QTransform_Bool) -> Qt.Action(Unit):
  Qt.Action.fail(Unit, 37, "Output scope body failed")

def transform(+value: Qt.QTransform) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Outputs_QTransform_Bool.with(Unit, Qt.QTransform.inverted(value), inverse_result)
    before: U32 <- Qt.Runtime.liveObjects()
    failed: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.Outputs_QTransform_Bool.with(Unit, Qt.QTransform.inverted(value), fail_inverse))
    expect_error(Unit, failed, 37)
    after: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(before, after), "Failed output scope leaked returned value")
    identity: Bool <- Qt.QTransform.isIdentity(value)
    require(identity, "Output cleanup destroyed the input handle")

def validation_result(value: Qt.Outputs_QValidator_State_String_Int32) -> Qt.Action(Unit):
  match value:
    case Qt.Outputs_QValidator_State_String_Int32{state, text, position}:
      require(U32.is_eq(Qt.QValidator.State.word(state), Qt.QValidator.State.word(Qt.QValidator.State.Acceptable())) && String.eq(text, "42") && U32.is_eq(Qt.Int32.word(position), 1), "Mutable string/scalar reference result changed")

def validation_invalid(value: Qt.Outputs_QValidator_State_String_Int32) -> Qt.Action(Unit):
  match value:
    case Qt.Outputs_QValidator_State_String_Int32{state, text, position}:
      require(U32.is_eq(Qt.QValidator.State.word(state), Qt.QValidator.State.word(Qt.QValidator.State.Invalid())) && String.eq(text, "音符🎵") && U32.is_eq(Qt.Int32.word(position), 2), "Reference conversion lost Unicode or input position")

def validator(+value: Qt.QIntValidator) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Outputs_QValidator_State_String_Int32.with(Unit, Qt.QIntValidator.validate(value, "42", Qt.Int32{1}), validation_result)
    Qt.Outputs_QValidator_State_String_Int32.with(Unit, Qt.QIntValidator.validate(value, "音符🎵", Qt.Int32{2}), validation_invalid)

def fixed_text(value: Qt.Outputs_String) -> Qt.Action(Unit):
  match value:
    case Qt.Outputs_String{text}:
      require(String.eq(text, "-1234.68"), "Mutable QString output did not preserve native changes")

def fixer_locale(+validator: Qt.QDoubleValidator, locale: Qt.QLocale) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QDoubleValidator.setLocale(validator, locale)
    Qt.QDoubleValidator.setNotation(validator, Qt.QDoubleValidator.Notation.StandardNotation())
    Qt.QDoubleValidator.setDecimals(validator, Qt.Int32{2})
    Qt.Outputs_String.with(Unit, Qt.QDoubleValidator.fixup(validator, "-1234.6789"), fixed_text)

def fixer(validator: Qt.QDoubleValidator) -> Qt.Action(Unit):
  Qt.QLocale.with(Unit, Qt.QLocale.c(), locale => fixer_locale(validator, locale))

def changed_position(value: Qt.Outputs_QValidator_State_String_Int32) -> Qt.Action(Unit):
  match value:
    case Qt.Outputs_QValidator_State_String_Int32{state, text, position}:
      require(U32.is_eq(Qt.QValidator.State.word(state), Qt.QValidator.State.word(Qt.QValidator.State.Invalid())) && String.eq(text, "abc") && U32.is_eq(Qt.Int32.word(position), 3), "Mutable scalar reference did not return native changes")

def regex_validator(value: Qt.QRegularExpressionValidator) -> Qt.Action(Unit):
  Qt.Outputs_QValidator_State_String_Int32.with(Unit, Qt.QRegularExpressionValidator.validate(value, "abc", Qt.Int32{1}), changed_position)

def regex(value: Qt.QRegularExpression) -> Qt.Action(Unit):
  Qt.QRegularExpressionValidator.with(Unit, Qt.QRegularExpressionValidator.new__QRegularExpression(value), regex_validator)

def swapped(+left: Qt.QByteArray, +right: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QByteArray.swap(left, right)
    a: String <- Qt.QByteArray.utf8(left)
    b: String <- Qt.QByteArray.utf8(right)
    require(String.eq(a, "right🎵") && String.eq(b, "left"), "Mutable handle reference did not update both values")
    Qt.QByteArray.swap(left, left)
    same: String <- Qt.QByteArray.utf8(left)
    require(String.eq(same, "right🎵"), "Self-aliasing mutable reference changed value")
    bad: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QByteArray.swap(left, Qt.QByteArray{0}))
    expect_error(Unit, bad, 116)
    unchanged: String <- Qt.QByteArray.utf8(left)
    require(String.eq(unchanged, "right🎵"), "Invalid mutable argument mutated receiver")

def swap_left(left: Qt.QByteArray) -> Qt.Action(Unit):
  Qt.QByteArray.with(Unit, Qt.QByteArray.fromUtf8("right🎵"), right => swapped(left, right))

def point_result(+original: Qt.QPoint, +copy: Qt.QPoint) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    x: Qt.Int32 <- Qt.QPoint.x(original)
    y: Qt.Int32 <- Qt.QPoint.y(original)
    copy_x: Qt.Int32 <- Qt.QPoint.x(copy)
    require(U32.is_eq(Qt.Int32.word(x), 5) && U32.is_eq(Qt.Int32.word(y), 8) && U32.is_eq(Qt.Int32.word(copy_x), 5), "Compound operator failed")
    require(U32.is_ne(Qt.QPoint.word(original), Qt.QPoint.word(copy)), "Mutable value return should be an owning snapshot")

def point_rhs(+left: Qt.QPoint, right: Qt.QPoint) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QPoint.with(Unit, Qt.QPoint.op_add_assign(left, right), copy => point_result(left, copy))
    x: Qt.Int32 <- Qt.QPoint.x(left)
    require(U32.is_eq(Qt.Int32.word(x), 5), "Operator snapshot cleanup destroyed the receiver")

def point_left(left: Qt.QPoint) -> Qt.Action(Unit):
  Qt.QPoint.with(Unit, Qt.QPoint.new__Int32_Int32(Qt.Int32{3}, Qt.Int32{5}), right => point_rhs(left, right))

def no_native_copy(value: Qt.QTemporaryFile) -> Qt.Action(Unit):
  require(U32.is_eq(Qt.QTemporaryFile.word(value), 0), "Already-native file unexpectedly needed a copy")

def native_file(value: Qt.QFile) -> Qt.Action(Unit):
  Qt.QTemporaryFile.with(Unit, Qt.QTemporaryFile.createNativeFile__QFile(value), no_native_copy)

def temporary_copy(+value: Qt.QTemporaryFile) -> Qt.Action(String):
  do Qt.Action<String>:
    require(U32.is_ne(Qt.QTemporaryFile.word(value), 0), "Qt resource did not produce a native temporary file")
    automatic: Bool <- Qt.QTemporaryFile.autoRemove(value)
    +path: String <- Qt.QTemporaryFile.fileName(value)
    exists: Bool <- Qt.QFile.exists__String(path)
    size: Qt.Int64 <- Qt.QTemporaryFile.size(value)
    require(automatic && exists && U32.is_ne(Qt.Int64.lo(size), 0), "Native file copy is absent, empty or not automatically removed")
    # The same public mutable-reference overload must return null for an
    # already-native input. A null result creates no owned resource.
    Qt.QFile.with(Unit, Qt.QFile.new__String(path), native_file)
    return path

def resource_file(+source: Qt.QFile) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    path: String <- Qt.QTemporaryFile.with(String, Qt.QTemporaryFile.createNativeFile__QFile(source), value => temporary_copy(value))
    survives: Bool <- Qt.QFile.exists(source)
    copied: Bool <- Qt.QFile.exists__String(path)
    require(survives && Bool.not(copied), "Factory scope failed to remove copied file or invalidated its input reference")

def resource_factory() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    # This file is shipped inside the Qt 6.12 Widgets library. It exercises
    # the factory's non-native-resource branch without a consumer C++ helper.
    +resource: String = ":/qt-project.org/styles/commonstyle/images/file-16.png"
    Qt.QFile.with(Unit, Qt.QFile.new__String(resource), source => resource_file(source))
    path: String <- Qt.QTemporaryFile.with(String, Qt.QTemporaryFile.createNativeFile__String(resource), value => temporary_copy(value))
    copied: Bool <- Qt.QFile.exists__String(path)
    require(Bool.not(copied), "String factory overload leaked its owned temporary file")
    invalid: Result<&1, &1, U32 & String, Qt.QTemporaryFile> <- Qt.Action.attempt(Qt.QTemporaryFile, Qt.QTemporaryFile.createNativeFile__QFile(Qt.QFile{0}))
    expect_error(Qt.QTemporaryFile, invalid, 116)

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QColor.with(Unit, Qt.QColor.new__Int32_Int32_Int32_Int32(Qt.Int32{17}, Qt.Int32{41}, Qt.Int32{93}, Qt.Int32{127}), color)
    Qt.QRect.with(Unit, Qt.QRect.new__Int32_Int32_Int32_Int32(Qt.Int32.neg(3), Qt.Int32{9}, Qt.Int32{20}, Qt.Int32{30}), rect)
    Qt.QByteArray.with(Unit, Qt.QByteArray.fromUtf8("42"), number)
    Qt.QByteArray.with(Unit, Qt.QByteArray.fromUtf8("not a number"), invalid_number)
    Qt.QTransform.with(Unit, Qt.QTransform.new(), value => transform(value))
    Qt.QIntValidator.with(Unit, Qt.QIntValidator.new__Int32_Int32(Qt.Int32{0}, Qt.Int32{100}), value => validator(value))
    Qt.QDoubleValidator.with(Unit, Qt.QDoubleValidator.new(), fixer)
    Qt.QRegularExpression.with(Unit, Qt.QRegularExpression.new__String("[0-9]+"), regex)
    Qt.QByteArray.with(Unit, Qt.QByteArray.fromUtf8("left"), swap_left)
    Qt.QPoint.with(Unit, Qt.QPoint.new__Int32_Int32(Qt.Int32{2}, Qt.Int32{3}), point_left)
    resource_factory()
    objects: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(objects, 0) && U32.is_eq(connections, 0), "Reference/output scopes leaked resources")
    Qt.Action.lift(Unit, IO.print("QT612_REFERENCES_OK scalar_outputs=1 mutable_refs=1 aliasing=1 output_cleanup=1 operators=1 native_factory=1 objects=0 connections=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, demo()))
