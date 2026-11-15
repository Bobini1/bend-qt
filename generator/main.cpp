// Maintainer-only frontend. Links the unmodified Shiboken ApiExtractor.
#include <apiextractor.h>
#include <apiextractorresult.h>
#include <abstractmetaargument.h>
#include <abstractmetaenum.h>
#include <abstractmetafield.h>
#include <abstractmetafunction.h>
#include <abstractmetalang.h>
#include <abstractmetatype.h>
#include <complextypeentry.h>
#include <enumtypeentry.h>
#include <flagstypeentry.h>
#include <optionsparser.h>
#include <reporthandler.h>
#include <parser/enumvalue.h>
#include <typedatabase.h>
#include <modifications.h>
#include <codesnip.h>
#include <typedefentry.h>
#include <sourcelocation.h>
#include <QtCore/QCoreApplication>
#include <QtCore/QFile>
#include <QtCore/QJsonArray>
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonObject>
#include <QtCore/QTextStream>
#include <algorithm>
#include <exception>

static QJsonObject typeJson(const AbstractMetaType &t)
{
    QJsonArray instantiations;
    for (const auto &i : t.instantiations()) instantiations.append(typeJson(i));
    QJsonObject result{{"cpp", t.cppSignature()},
            {"name", t.typeEntry()->qualifiedCppName()},
            {"const", t.isConstant()},
            {"reference", int(t.referenceType())},
            {"pointers", t.indirections()},
            {"enum", t.isEnum()}, {"flags", t.isFlags()},
            {"container", t.isContainer()}, {"instantiations", instantiations},
            {"array", t.isArray()}};
    if (t.isArray()) {
        result.insert("array_count", t.arrayElementCount());
        if (const auto *element = t.arrayElementType()) result.insert("array_element", typeJson(*element));
    }
    return result;
}

static QJsonObject fieldJson(const AbstractMetaField &f)
{
    return {{"name", f.originalName().isEmpty() ? f.name() : f.originalName()},
            {"binding_name", f.name()}, {"type", typeJson(f.type())},
            {"public", !f.isPrivate() && !f.isProtected()},
            {"private", f.isPrivate()}, {"protected", f.isProtected()},
            {"static", f.isStatic()}, {"removed", f.isModifiedRemoved()},
            {"getter", f.canGenerateGetter()}, {"setter", f.canGenerateSetter()},
            {"getter_enabled", f.isGetterEnabled()}, {"setter_enabled", f.isSetterEnabled()},
            {"declaring_class", f.enclosingClass() ? f.enclosingClass()->qualifiedCppName() : QString()}};
}

static QJsonObject enumJson(const AbstractMetaEnum &e)
{
    QJsonArray values;
    for (const auto &v : e.values())
        values.append(QJsonObject{{"name", v.name()}, {"value", v.value().toString()}});
    const auto flags = e.typeEntry()->flags();
    return {{"name", e.qualifiedCppName()}, {"signed", e.isSigned()},
            {"public", !e.isPrivate() && !e.isProtected()}, {"private", e.isPrivate()},
            {"protected", e.isProtected()}, {"anonymous", e.isAnonymous()}, {"package", e.package()},
            {"flags", flags ? flags->qualifiedCppName() : QString()},
            {"underlying_type", e.underlyingType()}, {"used_bits", e.usedBits()}, {"values", values}};
}

static QJsonObject functionJson(const AbstractMetaFunctionCPtr &f,
                                const AbstractMetaClassCPtr &c = {})
{
    QJsonArray arguments, policies, snippets;
    for (const auto &a : f->arguments()) {
        arguments.append(QJsonObject{{"name", a.name()}, {"type", typeJson(a.type())},
                                     {"default", a.defaultValueExpression()},
                                     {"native_default", a.originalDefaultValueExpression()},
                                     {"removed", f->argumentRemoved(a.argumentIndex() + 1)},
                                     {"array", f->isModifiedToArray(a.argumentIndex() + 1)}});
    }
    for (const auto &snippet : f->injectedCodeSnips(TypeSystem::CodeSnipPositionAny, TypeSystem::TargetLangCode))
        snippets.append(snippet.code());
    for (const auto &mod : f->modifications(c)) {
        for (const auto &arg : mod.argument_mods()) {
            QJsonArray references;
            for (const auto &ref : arg.referenceCounts())
                references.append(QJsonObject{{"action", int(ref.action)}, {"variable", ref.varName}});
            policies.append(QJsonObject{{"index", arg.index()},
                {"target_ownership", int(arg.targetOwnerShip())},
                {"native_ownership", int(arg.nativeOwnership())},
                {"parent_action", int(arg.owner().action)}, {"parent_index", arg.owner().index},
                {"reference_count", !arg.referenceCounts().isEmpty()},
                {"references", references},
                {"conversion", !arg.conversionRules().isEmpty()},
                {"modified_type", arg.modifiedType()}});
        }
    }
    return QJsonObject{
        {"name", f->originalName()}, {"signature", f->signature()},
        {"minimal_signature", f->minimalSignature()},
        {"source_file", f->sourceLocation().fileName()},
        {"source_line", f->sourceLocation().lineNumber()},
        {"source_signatures", QJsonArray::fromStringList(f->unresolvedSignatures())},
        {"return", typeJson(f->type())}, {"arguments", arguments},
        {"public", f->isPublic()}, {"protected", f->isProtected()}, {"private", f->isPrivate()},
        {"static", !c || c->isNamespace() || f->isStatic()},
        {"final_cpp", f->cppAttributes().testFlag(FunctionAttribute::Final)},
        {"noexcept", f->exceptionSpecification() == ExceptionSpecification::NoExcept},
        {"const", f->isConstant()}, {"virtual", f->isVirtual()},
        {"abstract", f->isAbstract()}, {"constructor", f->isConstructor()},
        {"copy_constructor", f->isCopyConstructor()},
        {"destructor", f->isDestructor()}, {"operator", f->isOperatorOverload()},
        {"signal", f->isSignal()}, {"slot", f->isSlot()},
        {"removed", f->isModifiedRemoved()}, {"deprecated", f->isDeprecated()},
        {"user_added", f->isUserAdded()}, {"injected_code", f->hasInjectedCode()},
        {"signature_modified", f->hasSignatureModifications()}, {"policies", policies}, {"snippets", snippets},
        {"rvalue_reference", f->usesRValueReferences()},
        {"implementing_class", f->implementingClass() ? f->implementingClass()->qualifiedCppName() : QString()},
        {"declaring_class", f->declaringClass() ? f->declaringClass()->qualifiedCppName() : QString()}
    };
}

int main(int argc, char **argv)
{
    QCoreApplication app(argc, argv);
    const auto args = app.arguments();
    if (args.size() < 6) {
        QTextStream(stderr) << "Usage: bend-qt-extract HEADER TYPESYSTEM OUTPUT LOGDIR INCLUDE...\n";
        return 2;
    }
    try {
        ReportHandler::startTimer();
        ApiExtractor extractor;
        extractor.setCppFileNames({QFileInfo(args[1])});
        extractor.setTypeSystem(args[2]);
        extractor.setLogDirectory(args[4]);
        auto options = extractor.createOptionsParser();
        options->handleOption("language-level", "c++17", OptionSource::CommandLine);
        options->handleOption("include-paths", args.mid(5).join(':'), OptionSource::CommandLine);
        options->handleOption("clang-option", "-DQT_NO_VERSION_TAGGING", OptionSource::CommandLine);
        TypeDatabase::setApiVersion("*", BQT_QT_API_VERSION);
        const auto result = extractor.run(ApiExtractorFlag::UsePySideExtensions
                                         | ApiExtractorFlag::AvoidProtectedHack);
        if (!result) {
            QTextStream(stderr) << "Shiboken extraction failed\n";
            return 1;
        }
        auto classes = result->classes();
        std::sort(classes.begin(), classes.end(), [](const auto &a, const auto &b) {
            return a->qualifiedCppName() < b->qualifiedCppName();
        });
        QJsonArray jsonClasses;
        for (const auto &c : classes) {
            QJsonArray functions, enums, bases, fields;
            for (const auto &b : c->baseClasses())
                bases.append(b->qualifiedCppName());
            for (const auto &e : c->enums())
                enums.append(enumJson(e));
            auto members = c->fields();
            std::sort(members.begin(), members.end(), [](const auto &a, const auto &b) {
                return a.originalName() < b.originalName();
            });
            for (const auto &field : members) fields.append(fieldJson(field));
            auto methods = c->functions();
            std::sort(methods.begin(), methods.end(), [](const auto &a, const auto &b) {
                return a->signature() < b->signature();
            });
            for (const auto &f : methods)
                functions.append(functionJson(f, c));
            jsonClasses.append(QJsonObject{
                {"name", c->qualifiedCppName()}, {"namespace", c->isNamespace()},
                {"source_file", c->sourceLocation().fileName()},
                {"source_line", c->sourceLocation().lineNumber()},
                {"package", c->typeEntry()->targetLangPackage()},
                {"generate", c->typeEntry()->generateCode()}, {"value", c->typeEntry()->isValue()},
                {"template", !c->templateArguments().isEmpty()},
                {"copyable", !c->hasDeletedCopyConstructor() && !c->hasPrivateCopyConstructor()},
                {"abstract", c->isAbstract()}, {"object", c->typeEntry()->isObject()},
                {"final_cpp", c->attributes().testFlag(AbstractMetaClass::FinalCppClass)},
                {"virtual_destructor", c->hasVirtualDestructor()},
                {"qobject", isQObject(c)},
                {"public_destructor", !c->hasPrivateDestructor() && !c->hasProtectedDestructor()},
                {"bases", bases}, {"enums", enums}, {"functions", functions}, {"fields", fields}
            });
        }
        QJsonArray enums;
        for (const auto &e : result->globalEnums())
            enums.append(enumJson(e));
        auto globalFunctions = result->globalFunctions();
        std::sort(globalFunctions.begin(), globalFunctions.end(), [](const auto &a, const auto &b) {
            return a->signature() < b->signature();
        });
        QJsonArray functions;
        for (const auto &f : globalFunctions) functions.append(functionJson(f));
        QJsonObject typedefs;
        for (const auto &entry : TypeDatabase::instance()->typedefEntries())
            typedefs.insert(entry->qualifiedCppName(), entry->sourceType());
        const QJsonObject document{{"schema", 1}, {"extractor", "Shiboken ApiExtractor " BQT_SHIBOKEN_VERSION},
                                   {"shiboken_commit", BQT_SHIBOKEN_COMMIT},
                                   {"qt_headers", QT_VERSION_STR}, {"qt_runtime", qVersion()},
                                   {"classes", jsonClasses}, {"global_functions", functions}, {"enums", enums}, {"typedefs", typedefs}};
        QFile output(args[3]);
        if (!output.open(QIODevice::WriteOnly)
            || output.write(QJsonDocument(document).toJson()) < 0)
            return 1;
        QTextStream(stdout) << "Extracted " << jsonClasses.size() << " classes with Shiboken\n";
        return 0;
    } catch (const std::exception &error) {
        QTextStream(stderr) << error.what() << '\n';
        return 1;
    }
}

